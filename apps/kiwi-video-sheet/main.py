# main.py
"""きうい動画一覧シート - Main GUI application."""
import os
import sys
import threading
import tkinter as tk
from tkinter import ttk, messagebox, filedialog

# Common path insertion for non-frozen execution
if not getattr(sys, 'frozen', False):
    _common_dir = os.path.join(os.path.dirname(__file__), '..', 'common')
    if os.path.isdir(_common_dir) and _common_dir not in sys.path:
        sys.path.insert(0, _common_dir)

from consumer_ui import Window  # noqa: E402
import core
import layout  # noqa: E402


class App(Window):
    def __init__(self):
        super().__init__(
            title='きうい動画一覧シート',
            subtitle='動画をひと目で見渡せる、時刻付きの一覧画像を作ります。',
            engine=core.ENGINE
        )

        # Adjust geometry for 1080x730 min 940x680
        self.geometry('1080x730')
        self.minsize(940, 680)

        # State
        self.result = None  # dict from core.render
        self.saved_path = None
        self.details_window = None
        self.details_vars = {k: tk.StringVar(value=v) for k, v in {
            'start': '0', 'end': '0', 'theme': '明るい',
            'show_title': 'あり', 'show_times': 'あり'}.items()}

        # Main form fields (5 rows max: input, count, columns, width, format)
        self.field('input', '動画ファイル', picker=[('動画', '*.mp4 *.mov *.mkv *.webm *.avi *.m4v *.mpg *.mpeg *.ts')])
        self.field('count', '枚数 (4-36)', value='12')
        self.field('columns', '列数 (2-6)', value='4')
        self.field('width', '1コマの幅 (160～480px)', value='240')
        self.field('format', '出力形式', choices=['PNG', 'JPEG'], value='PNG')

        # Action buttons (use existing self.actions frame)
        self.btn_make = self.button(self.actions, '一覧を作る', self.on_make)
        self.btn_preview = self.button(self.actions, '画像を確認', self.on_preview)
        self.btn_save = self.button(self.actions, '別名で保存', self.on_save)
        self.btn_open = self.button(self.actions, '保存先を開く', self.on_open_folder)
        self.btn_details = self.button(self.actions, '詳細設定…', self.on_details)

        for b in (self.btn_make, self.btn_preview, self.btn_save, self.btn_open, self.btn_details):
            b.pack(side='left', padx=2)

        for key, var in self.vars.items():
            if key != 'format':
                var.trace_add('write', self.invalidate)
        for var in self.details_vars.values():
            var.trace_add('write', self.invalidate)
        self.note.set('1動画512 MiB・60分まで。4～36コマを一覧画像にします。初回のみFFmpeg公式サイトが案内するGyan版約100 MBを取得。元動画は変更しません。')
        self.show('動画と配置を選んで「一覧を作る」を押します。\n「画像を確認」で仕上がりを見てから、PNG・JPEGで別名保存できます。')
        self._update_action_states()

    def _get_options(self):
        """Collect and validate options from GUI vars."""
        vals = self.values()

        # Input path
        input_path = vals.get('input', '').strip()
        if input_path:
            input_path = str(core.safe_path(input_path))
        if not input_path or not os.path.isfile(input_path):
            raise ValueError("有効な動画ファイルを選択してください")

        # Numeric fields
        try:
            count = int(vals['count'])
            columns = int(vals['columns'])
            width = int(vals['width'])
        except (ValueError, KeyError):
            raise ValueError("枚数・列数・幅は整数で入力してください")

        if not (4 <= count <= 36):
            raise ValueError("枚数は4〜36の範囲で指定してください")
        if not (2 <= columns <= 6):
            raise ValueError("列数は2〜6の範囲で指定してください")
        if not (160 <= width <= 480):
            raise ValueError("幅は160〜480の範囲で指定してください")

        # Details vars (retained from modal)
        start = self.details_vars['start'].get()
        end = self.details_vars['end'].get()
        theme = self.details_vars['theme'].get()
        show_title = self.details_vars['show_title'].get() == 'あり'
        show_times = self.details_vars['show_times'].get() == 'あり'

        try:
            start_f = float(start) if start else 0.0
            end_f = float(end) if end else 0.0
        except ValueError:
            raise ValueError("開始/終了時間は数値で入力してください")

        if not (0 <= start_f <= 3600):
            raise ValueError("開始時間は0〜3600秒の範囲で指定してください")
        if not (0 <= end_f <= 3600):
            raise ValueError("終了時間は0〜3600秒の範囲で指定してください")

        fmt = vals.get('format', 'PNG')
        if fmt not in ('PNG', 'JPEG'):
            raise ValueError("出力形式はPNGまたはJPEGを指定してください")

        return {
            'path': input_path,
            'count': count,
            'columns': columns,
            'width': width,
            'start': start_f,
            'end': end_f,
            'theme': theme,
            'show_title': show_title,
            'show_times': show_times,
            'format': fmt
        }

    def on_make(self):
        """Start rendering job."""
        if self.busy:
            return
        try:
            opts = self._get_options()
        except ValueError as e:
            messagebox.showerror('入力エラー', str(e), parent=self)
            return

        # Invalidate previous result
        self.invalidate()

        def job():
            return core.render(
                path=opts['path'],
                options={k: v for k, v in opts.items() if k != 'path' and k != 'format'},
                cancel=self.cancel,
                progress=lambda message: self.events.put(('status', str(message)))
            )

        def done(result):
            if result is None or 'png' not in result:
                raise ValueError("レンダリング結果が不正です")
            self.result = result
            self.show(result['text'])
            self.saved_path = None
            self._update_action_states()
            self.status.set('一覧を作成しました。')

        self.start(job, done)

    def on_preview(self):
        """Show scaled preview."""
        if self.busy:
            return
        if not self.result or 'png' not in self.result:
            messagebox.showinfo('プレビュー', 'まだ一覧が作成されていません。', parent=self)
            return

        try:
            from PIL import Image
            import io

            png_bytes = self.result['png']
            img = Image.open(io.BytesIO(png_bytes))

            # Scale to <=1000x650
            max_w, max_h = 1000, 650
            ratio = min(max_w / img.width, max_h / img.height, 1.0)
            if ratio < 1.0:
                new_size = (int(img.width * ratio), int(img.height * ratio))
                img = img.resize(new_size, Image.Resampling.LANCZOS)

            # Convert to PNG bytes for PhotoImage
            buf = io.BytesIO()
            img.save(buf, format='PNG')
            preview_bytes = buf.getvalue()

            self.picture(preview_bytes)
        except Exception as e:
            messagebox.showerror('プレビューエラー', f'画像を表示できませんでした:\n{e}', parent=self)

    def on_save(self):
        """Save result to selected folder."""
        if self.busy:
            return
        if not self.result or 'png' not in self.result:
            messagebox.showinfo('保存', 'まだ一覧が作成されていません。', parent=self)
            return

        folder = self.choose_save()
        if not folder:
            return

        fmt = self.values().get('format', 'PNG')

        def job():
            return core.save(
                result=self.result,
                folder=folder,
                format=fmt,
                cancel=self.cancel
            )

        def done(path):
            if not path:
                raise ValueError("保存に失敗しました")
            self.saved_path = path
            self.status.set(f'保存しました: {os.path.basename(path)}')
            self.show(f'保存先:\n{path}')

        self.start(job, done)

    def on_open_folder(self):
        """Open saved folder in Explorer."""
        if self.busy:
            return
        if not self.saved_path:
            messagebox.showinfo('フォルダを開く', 'まだ保存されていません。', parent=self)
            return

        try:
            folder = os.path.dirname(self.saved_path)
            os.startfile(folder)
        except Exception as e:
            messagebox.showerror('フォルダを開けませんでした', str(e), parent=self)

    def on_details(self):
        """Open details modal dialog."""
        if self.busy:
            return

        # Create or reuse details window
        if self.details_window and self.details_window.winfo_exists():
            self.details_window.lift()
            self.details_window.focus_force()
            return

        top = tk.Toplevel(self)
        top.title('詳細設定')
        top.geometry('400x350')
        top.transient(self)
        top.grab_set()

        frame = ttk.Frame(top, padding=16)
        frame.pack(fill='both', expand=True)

        # Retain vars if they exist, else create new
        if not self.details_vars:
            self.details_vars['start'] = tk.StringVar(value='0')
            self.details_vars['end'] = tk.StringVar(value='0')
            self.details_vars['theme'] = tk.StringVar(value='明るい')
            self.details_vars['show_title'] = tk.StringVar(value='あり')
            self.details_vars['show_times'] = tk.StringVar(value='あり')

        row = 0
        ttk.Label(frame, text='開始時間 (秒, 0=全体)').grid(row=row, column=0, sticky='w', pady=5)
        ttk.Entry(frame, textvariable=self.details_vars['start']).grid(row=row, column=1, sticky='ew', pady=5)
        row += 1

        ttk.Label(frame, text='終了時間 (秒, 0=全体)').grid(row=row, column=0, sticky='w', pady=5)
        ttk.Entry(frame, textvariable=self.details_vars['end']).grid(row=row, column=1, sticky='ew', pady=5)
        row += 1

        ttk.Label(frame, text='テーマ').grid(row=row, column=0, sticky='w', pady=5)
        ttk.Combobox(frame, textvariable=self.details_vars['theme'], values=['明るい', '暗い'], state='readonly').grid(row=row, column=1, sticky='ew', pady=5)
        row += 1

        ttk.Label(frame, text='タイトル表示').grid(row=row, column=0, sticky='w', pady=5)
        ttk.Combobox(frame, textvariable=self.details_vars['show_title'], values=['あり', 'なし'], state='readonly').grid(row=row, column=1, sticky='ew', pady=5)
        row += 1

        ttk.Label(frame, text='時刻表示').grid(row=row, column=0, sticky='w', pady=5)
        ttk.Combobox(frame, textvariable=self.details_vars['show_times'], values=['あり', 'なし'], state='readonly').grid(row=row, column=1, sticky='ew', pady=5)
        row += 1

        frame.columnconfigure(1, weight=1)

        def on_close():
            top.grab_release()
            top.destroy()
            self.details_window = None

        ttk.Button(frame, text='OK', command=on_close).grid(row=row, column=0, columnspan=2, pady=(15, 0))

        top.protocol('WM_DELETE_WINDOW', on_close)
        self.details_window = top

    def invalidate(self, *args):
        """Clear cached result and stale preview/save state."""
        self.result = None
        for child in self.winfo_children():
            if isinstance(child, tk.Toplevel) and child.title() == 'プレビュー':
                child.destroy()
        self._update_action_states()

    def poll(self):
        super().poll()
        if not self.closing and not self.busy:
            self._update_action_states()

    def _update_action_states(self):
        """Enable/disable action buttons based on result state."""
        has_result = self.result is not None and 'png' in self.result
        preview_state = 'normal' if has_result else 'disabled'
        save_state = 'normal' if has_result else 'disabled'
        open_state = 'normal' if self.saved_path else 'disabled'

        # Find buttons by text (simple approach since we don't have direct refs)
        for widget, _ in self.controls:
            try:
                txt = widget.cget('text')
                if txt == '画像を確認':
                    widget.configure(state=preview_state)
                elif txt == '別名で保存':
                    widget.configure(state=save_state)
                elif txt == '保存先を開く':
                    widget.configure(state=open_state)
            except (tk.TclError, AttributeError):
                pass


if __name__ == '__main__':
    app = App()
    app.mainloop()
