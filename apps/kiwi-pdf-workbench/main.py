"""Edit PDFs and pass selected or edited documents directly to page export."""
import base64
import gc
import math
from pathlib import Path
import queue
import sys
import threading
import tkinter as tk
from tkinter import ttk, filedialog
if not getattr(sys, 'frozen', False):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'common'))
from consumer_runtime import safe_path
import editor
import pdf_images


class ImageDialog(tk.Toplevel):
    def __init__(self, parent, path, pages):
        super().__init__(parent)
        self.owner = parent
        self.path = str(path)
        self.closing = False
        self.controls = []
        self.vars = {}
        self.title('PDFの表示・画像・テキスト保存')
        self.geometry('840x860')
        self.minsize(760, 760)
        body = ttk.Frame(self, padding=14)
        body.pack(fill='both', expand=True)
        ttk.Label(body, text='PDFの表示・書き出し', font=('Yu Gothic UI', 17, 'bold')).pack(anchor='w')
        self.file_name = tk.StringVar(value=Path(path).name)
        ttk.Label(body, textvariable=self.file_name, wraplength=790).pack(anchor='w', pady=8)
        row = ttk.Frame(body)
        row.pack(fill='x')
        self.button(row, '別のPDFを選ぶ…', self.choose).pack(side='left')
        self.button(row, '画像エンジンを準備（初回のみ）', self.setup).pack(side='left', padx=10)
        form = ttk.Frame(body)
        form.pack(fill='x', pady=12)
        form.columnconfigure(1, weight=1)
        fields = [('pages', 'ページ（例：1-3,5）', pages, None),
                  ('format', '保存形式', 'PNG画像（ZIP）', ['PNG画像（ZIP）', 'テキスト']),
                  ('dpi', '画像の解像度（dpi）', '144', ['72', '96', '144', '200', '300']),
                  ('color', '画像の色', 'カラー', ['カラー', 'グレー']),
                  ('rotation', '時計回りに回転', '0', ['0', '90', '180', '270'])]
        for i, (key, label, default, choices) in enumerate(fields):
            self.vars[key] = tk.StringVar(value=default)
            ttk.Label(form, text=label).grid(row=i, column=0, sticky='w', pady=5, padx=(0, 15))
            state = 'readonly' if choices else 'normal'
            widget = ttk.Combobox(form, textvariable=self.vars[key], values=choices, state=state) if choices else ttk.Entry(form, textvariable=self.vars[key])
            widget.grid(row=i, column=1, sticky='ew', pady=5)
            self.controls.append((widget, state))
        row = ttk.Frame(body)
        row.pack(fill='x')
        self.button(row, '最初の指定ページを表示', self.preview).pack(side='left')
        self.button(row, '画像・テキストを保存…', self.save).pack(side='left', padx=10)
        self.stop = ttk.Button(row, text='停止', state='disabled', command=parent.stop)
        self.stop.pack(side='right')
        self.preview_box = ttk.Label(body, text='選択したPDFや、編集して作ったPDFをそのまま表示・書き出しできます。', anchor='center')
        self.preview_box.pack(fill='both', expand=True, pady=10)
        self.status = tk.StringVar(value='ページを指定して表示または保存してください。')
        ttk.Label(body, textvariable=self.status, wraplength=790).pack(anchor='w')
        ttk.Label(body, text='画像化は入力32 MiB・指定100ページ、長辺3,000pxまで。暗号化されたPDFは編集画面で解除したコピーを作ってからお使いください。', wraplength=790).pack(anchor='w', pady=(10, 0))
        self.protocol('WM_DELETE_WINDOW', self.close)

    def button(self, parent, text, command):
        widget = ttk.Button(parent, text=text, command=command)
        self.controls.append((widget, 'normal'))
        return widget

    def values(self):
        return {'input': self.path, **{key: v.get() for key, v in self.vars.items()}}

    def set_busy(self, busy):
        for widget, state in self.controls:
            widget.configure(state='disabled' if busy else state)
        self.stop.configure(state='normal' if busy else 'disabled')

    def choose(self):
        if self.owner.busy():
            return
        path = filedialog.askopenfilename(parent=self, filetypes=[('PDF', '*.pdf')])
        if path:
            self.owner.show_image_path(path, '1')

    def setup(self):
        self.owner.start_image(lambda: pdf_images.engine.install(self.owner.cancel, lambda text: self.owner.image_events.put(('progress', text))),
                               lambda _: self.status.set('画像エンジンを準備しました。'))

    def preview(self):
        values = self.values()
        def done(data):
            image = tk.PhotoImage(data=base64.b64encode(data).decode('ascii'))
            scale = max(1, math.ceil(image.width()/max(200, self.preview_box.winfo_width())),
                        math.ceil(image.height()/max(200, self.preview_box.winfo_height())))
            if scale > 1:
                image = image.subsample(scale, scale)
            self.preview_box.configure(image=image, text='')
            self.preview_box.image = image
            self.status.set('最初の指定ページを表示しました。')
        self.owner.start_image(lambda: pdf_images.render(values, None, self.owner.cancel, True), done)

    def save(self):
        if self.owner.busy():
            return
        folder = filedialog.askdirectory(parent=self, title='書き出し先フォルダー')
        if folder:
            values = self.values()
            self.owner.start_image(lambda: pdf_images.render(values, folder, self.owner.cancel),
                                   lambda path: self.status.set('保存しました：' + str(path)))

    def close(self):
        if self.owner.image_worker:
            self.closing = True
            self.owner.stop()
            self.status.set('停止してから閉じます…')
        else:
            self.destroy()
            self.owner.image_dialog = None

    def destroy(self):
        # Release Tcl-owned variables and images on the GUI thread, before a worker can run GC.
        if hasattr(self.preview_box, 'image'):
            self.preview_box.configure(image='')
            del self.preview_box.image
        self.vars.clear()
        self.file_name = None
        self.status = None
        super().destroy()
        self.controls.clear()


class App(editor.App):
    def __init__(self):
        self.image_worker = None
        self.image_dialog = None
        self.image_events = queue.Queue()
        super().__init__()
        self.title('きういPDF作業場')
        self.geometry('1060x830')
        self.minsize(980, 780)
        first = self.winfo_children()[0]
        bar = ttk.Frame(self, padding=(14, 8))
        bar.pack(side='bottom', fill='x', before=first)
        for text, command in [('選択PDFを表示・画像化', self.image_selected), ('作成PDFを表示・画像化', self.image_created)]:
            button = ttk.Button(bar, text=text, command=command)
            button.pack(side='left', padx=(0, 10))
            self.controls.append(button)
        ttk.Label(bar, text='編集したPDFを、そのままPNGやテキストへ。').pack(side='left')

    def busy(self):
        return super().busy() or self.image_worker is not None

    def set_busy(self, value):
        super().set_busy(value)
        if self.image_dialog and self.image_dialog.winfo_exists():
            self.image_dialog.set_busy(value)

    def show_image_path(self, path, pages='1', password=''):
        if self.busy():
            return
        try:
            source = safe_path(path)
            if not source.is_file() or source.suffix.lower() != '.pdf' or not 0 < source.stat().st_size <= 32*1024**2:
                raise ValueError('表示・画像化は32 MiB以下のPDFを指定してください。分割ZIPは直接渡せません。')
            if password:
                raise ValueError('暗号化されたPDFは「パスワードを解除」で別名保存し、作成PDFを画像化してください。')
            pdf_images.page_list(pages)
        except (ValueError, OSError) as error:
            self.status_var.set(str(error))
            return
        if self.image_dialog and self.image_dialog.winfo_exists():
            self.image_dialog.destroy()
        self.image_dialog = ImageDialog(self, source, pages)
        return self.image_dialog

    def image_selected(self):
        if self.busy():
            return
        try:
            row = self.selected_rows('extract')[0]
            return self.show_image_path(row['path'], row.get('pages') or '1', row.get('password', ''))
        except ValueError as error:
            self.status_var.set(str(error))

    def image_created(self):
        if self.last_output:
            return self.show_image_path(self.last_output)
        self.status_var.set('先にPDFを作成してください。')

    def launch(self, rows, op, destination, options):
        gc.collect()
        super().launch(rows, op, destination, options)

    def start_image(self, job, done):
        if self.busy() or not self.image_dialog:
            return
        gc.collect()
        self.cancel.clear()
        self.set_busy(True)
        self.image_dialog.set_busy(True)
        self.image_dialog.status.set('処理しています…')
        self.status_var.set('PDFの表示・書き出しを処理しています…')
        def worker():
            try:
                self.image_events.put(('done', (done, job())))
            except Exception as error:
                self.image_events.put(('error', str(error)))
        self.image_worker = threading.Thread(target=worker, daemon=True)
        self.image_worker.start()

    def poll(self):
        while True:
            try:
                kind, value = self.image_events.get_nowait()
            except queue.Empty:
                break
            if kind == 'progress':
                if self.image_dialog:
                    self.image_dialog.status.set(value)
                continue
            if self.image_worker:
                self.image_worker.join(timeout=1)
            self.image_worker = None
            self.set_busy(False)
            dialog = self.image_dialog
            if dialog and dialog.winfo_exists():
                dialog.set_busy(False)
                if dialog.closing or self.closing:
                    dialog.destroy()
                    self.image_dialog = None
                elif kind == 'error':
                    dialog.status.set(value[:500])
                    self.status_var.set(value[:500])
                else:
                    done, result = value
                    try:
                        done(result)
                        self.status_var.set('表示・書き出しが完了しました。')
                    except Exception as error:
                        dialog.status.set(str(error))
        super().poll()


if __name__ == '__main__':
    App().mainloop()
