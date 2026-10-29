"""Small Tk job shell; all GUI updates run on the main thread."""
import base64
import queue
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox


class Window(tk.Tk):
    def __init__(self, title, subtitle, engine):
        super().__init__()
        self.title(title)
        self.geometry('1080x790')
        self.minsize(940, 720)
        self.engine = engine
        self.cancel = threading.Event()
        self.events = queue.Queue()
        self.busy = False
        self.closing = False
        self.controls = []
        self.vars = {}
        self.body = ttk.Frame(self, padding=16)
        self.body.pack(fill='both', expand=True)
        ttk.Label(self.body, text=title, font=('Yu Gothic UI', 21, 'bold')).pack(anchor='w')
        ttk.Label(self.body, text=subtitle, wraplength=1000).pack(anchor='w', pady=(5, 12))
        self.button(self.body, 'エンジンを準備（初回のみ・公式配布を取得）', self.setup).pack(anchor='w', pady=(0, 10))
        self.form = ttk.Frame(self.body)
        self.form.pack(fill='x')
        self.form.columnconfigure(1, weight=1)
        self.row = 0
        self.actions = ttk.Frame(self.body)
        self.actions.pack(fill='x', pady=12)
        self.output = tk.Text(self.body, height=12, wrap='none', state='disabled', font=('Yu Gothic UI', 10))
        self.output.pack(fill='both', expand=True)
        bottom = ttk.Frame(self.body)
        bottom.pack(fill='x', pady=(12, 5))
        self.stop = ttk.Button(bottom, text='停止', command=self.cancel.set, state='disabled')
        self.stop.pack(side='left')
        self.status = tk.StringVar(value='元ファイルを残して、別名で保存します。')
        ttk.Label(bottom, textvariable=self.status, wraplength=900).pack(side='left', padx=12)
        self.note = tk.StringVar()
        ttk.Label(self.body, textvariable=self.note, wraplength=1020).pack(anchor='w')
        self.protocol('WM_DELETE_WINDOW', self.close)
        self.after(70, self.poll)

    def button(self, parent, text, command):
        b = ttk.Button(parent, text=text, command=command)
        self.controls.append((b, 'normal'))
        return b

    def field(self, key, label, value='', choices=None, picker=None):
        v = tk.StringVar(value=value)
        self.vars[key] = v
        ttk.Label(self.form, text=label).grid(row=self.row, column=0, sticky='w', pady=5, padx=(0, 15))
        state = 'readonly' if choices else 'normal'
        w = ttk.Combobox(self.form, textvariable=v, values=choices, state=state) if choices else ttk.Entry(self.form, textvariable=v)
        w.grid(row=self.row, column=1, sticky='ew', pady=5)
        self.controls.append((w, state))
        if picker:
            def pick():
                if self.busy:
                    return
                path = filedialog.askdirectory(parent=self) if picker == 'folder' else filedialog.askopenfilename(parent=self, filetypes=picker)
                if path:
                    v.set(path)
                    if hasattr(self, 'invalidate'):
                        self.invalidate()
            self.button(self.form, '選ぶ…', pick).grid(row=self.row, column=2, padx=(8, 0))
        self.row += 1
        return v

    def values(self):
        return {k: v.get() for k, v in self.vars.items()}

    def show(self, text):
        self.output.configure(state='normal')
        self.output.delete('1.0', 'end')
        self.output.insert('1.0', text[:500000])
        self.output.configure(state='disabled')

    def start(self, job, done):
        if self.busy:
            return
        self.busy = True
        self.cancel.clear()
        for widget, _ in self.controls:
            widget.configure(state='disabled')
        self.stop.configure(state='normal')
        self.status.set('処理しています…')
        def worker():
            try:
                self.events.put(('done', (done, job())))
            except Exception as error:
                self.events.put(('error', str(error)))
        threading.Thread(target=worker, daemon=True).start()

    def setup(self):
        self.start(lambda: self.engine.install(self.cancel, lambda msg: self.events.put(('status', msg))),
                   lambda result: self.status.set('準備できました。変換処理はPC内で行います。'))

    def poll(self):
        try:
            while True:
                kind, value = self.events.get_nowait()
                if kind == 'status':
                    self.status.set(value)
                    continue
                self.busy = False
                for widget, state in self.controls:
                    widget.configure(state=state)
                self.stop.configure(state='disabled')
                if self.closing:
                    self.destroy()
                    return
                if kind == 'error':
                    self.status.set(value[:300])
                    messagebox.showerror('処理できませんでした', value[:2500], parent=self)
                else:
                    done, result = value
                    try:
                        done(result)
                    except Exception as error:
                        self.status.set(str(error))
                        messagebox.showerror('結果を表示できませんでした', str(error), parent=self)
        except queue.Empty:
            pass
        self.after(70, self.poll)

    def choose_save(self):
        if self.busy:
            return None
        return filedialog.askdirectory(parent=self, title='保存先フォルダー') or None

    def picture(self, png):
        top = tk.Toplevel(self)
        top.title('プレビュー')
        image = tk.PhotoImage(data=base64.b64encode(png).decode('ascii'))
        label = ttk.Label(top, image=image)
        label.image = image
        label.pack(padx=12, pady=12)

    def close(self):
        if self.busy:
            self.closing = True
            self.cancel.set()
            self.status.set('処理を停止して終了します…')
        else:
            self.destroy()
