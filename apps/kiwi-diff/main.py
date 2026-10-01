"""UTF-8 file comparison GUI."""
import sys as _advanced_sys
from pathlib import Path as _AdvancedPath
if not getattr(_advanced_sys, "frozen", False):
    _advanced_sys.path.insert(0, str(_AdvancedPath(__file__).resolve().parents[1] / "common"))
from advanced import attach
import os
import queue
import threading
from pathlib import Path
from core import compare_files,resource_dir
import tkinter as tk
from tkinter import filedialog

APP_TITLE = "きうい比較"
APP_SIZE = "1000x720"
APP_MIN_SIZE = "800x550"
NOTICE_TEXT = (
    "構文比較では空白などの変更を無視する場合があります。"
    "文字として比較するにはプレーンテキストを選択。改行形式・BOMの違いは無視します。"
)
MAX_FILE_SIZE = 2 * 1024 * 1024


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(APP_TITLE)
        self.geometry(APP_SIZE)
        self.minsize(*map(int, APP_MIN_SIZE.split("x")))
        self.left = tk.StringVar()
        self.right = tk.StringVar()
        self.left_name = tk.StringVar()
        self.right_name = tk.StringVar()
        self.plain = tk.BooleanVar()
        self.status = tk.StringVar()
        self.running = False
        self.cancel=threading.Event()
        self.results=queue.Queue()
        self.worker=None
        self.status.set("待機中")
        self._build_ui()
        for variable in (self.left,self.right,self.plain):
            variable.trace_add("write",self._changed)
        self._poll()
        self.protocol("WM_DELETE_WINDOW", self.close)
        # Additional upstream operations run in a separate structured window.
        self.advanced = attach(self, source_dir=Path(__file__).resolve().parent)

    def _build_ui(self):
        top = tk.Frame(self)
        top.pack(fill="x", padx=8, pady=6)
        tk.Label(top, text="左ファイル:").grid(row=0, column=0, sticky="w")
        tk.Entry(top, textvariable=self.left_name, state="readonly").grid(
            row=0, column=1, sticky="we", padx=4
        )
        self.left_btn = tk.Button(top, text="選択", command=lambda: self.choose("left"))
        self.left_btn.grid(row=0, column=2, padx=4)
        tk.Label(top, text="右ファイル:").grid(row=1, column=0, sticky="w")
        tk.Entry(top, textvariable=self.right_name, state="readonly").grid(
            row=1, column=1, sticky="we", padx=4
        )
        self.right_btn = tk.Button(top, text="選択", command=lambda: self.choose("right"))
        self.right_btn.grid(row=1, column=2, padx=4)
        top.columnconfigure(1, weight=1)

        controls = tk.Frame(self)
        controls.pack(fill="x", padx=8, pady=4)
        self.mode_check = tk.Checkbutton(
            controls,
            text="プレーンテキスト",
            variable=self.plain,
        )
        self.mode_check.pack(side="left")
        self.compare_btn = tk.Button(controls, text="比較", command=self.start_compare)
        self.compare_btn.pack(side="left", padx=4)
        self.stop_btn = tk.Button(
            controls, text="停止", command=self.stop_compare, state="disabled"
        )
        self.stop_btn.pack(side="left", padx=4)
        self.copy_btn = tk.Button(controls, text="コピー", command=self.copy_output, state="disabled")
        self.copy_btn.pack(side="left", padx=4)
        self.save_btn = tk.Button(controls, text="保存", command=self.save_output, state="disabled")
        self.save_btn.pack(side="left", padx=4)
        tk.Label(controls, textvariable=self.status).pack(side="right")

        tk.Label(self, text=NOTICE_TEXT, wraplength=980).pack(fill="x", padx=8)
        tk.Label(self,text="赤：左ファイルの変更前　／　緑：右ファイルの変更後").pack(anchor='w',padx=8)

        out_frame = tk.Frame(self)
        out_frame.pack(fill="both", expand=True, padx=8, pady=6)
        self.output = tk.Text(out_frame, wrap="none", font=("Consolas", 10), state="disabled")
        self.output.tag_configure('removed',foreground='#a11919',background='#ffe7e7')
        self.output.tag_configure('added',foreground='#096126',background='#dff5e5')
        self.output.grid(row=0,column=0,sticky="nsew")
        out_frame.rowconfigure(0,weight=1)
        out_frame.columnconfigure(0,weight=1)
        hbar = tk.Scrollbar(out_frame, orient="horizontal", command=self.output.xview)
        vbar = tk.Scrollbar(out_frame, orient="vertical", command=self.output.yview)
        self.output.configure(xscrollcommand=hbar.set, yscrollcommand=vbar.set)
        hbar.grid(row=1,column=0,sticky="ew")
        vbar.grid(row=0,column=1,sticky="ns")


    def _clear(self):
        self.output.config(state='normal')
        self.output.delete('1.0','end')
        self.output.config(state='disabled')
        self.copy_btn.config(state='disabled')
        self.save_btn.config(state='disabled')

    def _changed(self,*args):
        self.left_name.set(Path(self.left.get()).name)
        self.right_name.set(Path(self.right.get()).name)
        if not self.running:
            self._clear()
            self.status.set('待機中')

    def choose(self,side):
        if self.running:
            return
        path=filedialog.askopenfilename(parent=self,title='UTF-8のファイルを選択')
        if path:
            (self.left if side=='left' else self.right).set(path)

    def start_compare(self):
        if self.running:
            return
        self._clear()
        if not self.left.get() or not self.right.get():
            self.status.set('左右のファイルを選んでください。')
            return
        self.running=True
        self.cancel.clear()
        for button in (self.left_btn,self.right_btn,self.compare_btn,self.mode_check):
            button.config(state='disabled')
        self.stop_btn.config(state='normal')
        self.status.set('比較中...')
        self.worker=threading.Thread(target=self._work,args=(Path(self.left.get()),Path(self.right.get()),self.plain.get()),daemon=True)
        self.worker.start()

    def _work(self,left,right,plain):
        try:
            result=compare_files(resource_dir()/'difft.exe',left,right,plain,self.cancel)
            self.results.put(('ok',result))
        except InterruptedError:
            self.results.put(('error','停止しました'))
        except TimeoutError:
            self.results.put(('error','20秒以内に比較できませんでした。'))
        except ValueError as exc:
            self.results.put(('error',str(exc)))
        except Exception:
            self.results.put(('error','比較できませんでした。ファイルやアクセス権を確認してください。'))

    def _poll(self):
        try:
            while True:
                kind,data=self.results.get_nowait()
                self.running=False
                for button in (self.left_btn,self.right_btn,self.compare_btn,self.mode_check):
                    button.config(state='normal')
                self.stop_btn.config(state='disabled')
                if kind=='ok':
                    self.output.config(state='normal')
                    for text,tag in data['segments']:
                        self.output.insert('end',text,(tag,) if tag else ())
                    self.output.config(state='disabled')
                    self.copy_btn.config(state='normal')
                    self.save_btn.config(state='normal')
                    self.status.set('差分あり' if data['changed'] else '比較モード上の差分なし')
                else:
                    self.status.set(data)
        except queue.Empty:
            pass
        self.after(100,self._poll)

    def stop_compare(self):
        if self.running:
            self.cancel.set()
            self.status.set('停止中...')

    def copy_output(self):
        text=self.output.get('1.0','end-1c')
        if self.running or not text:
            return
        self.clipboard_clear()
        self.clipboard_append(text)
        self.status.set('コピーしました')

    def save_output(self):
        text=self.output.get('1.0','end-1c')
        if self.running or not text:
            return
        filename=filedialog.asksaveasfilename(parent=self,title='比較結果を保存',defaultextension='.txt',filetypes=[('テキスト','*.txt')],initialfile='comparison.txt',confirmoverwrite=True)
        if not filename:
            return
        try:
            dest=Path(filename)
            for value in (self.left.get(),self.right.get()):
                source=Path(value)
                if dest.resolve()==source.resolve() or (dest.exists() and source.exists() and os.path.samefile(dest,source)):
                    self.status.set('入力ファイルと同じファイルには保存できません。')
                    return
            with dest.open('w',encoding='utf8',newline='\n') as stream:
                stream.write(text)
            self.status.set('比較結果を保存しました')
        except OSError:
            self.status.set('保存できませんでした。保存先やアクセス権を確認してください。')

    def close(self):
        self.cancel.set()
        if self.worker and self.worker.is_alive():
            self.worker.join(timeout=2)
        self.destroy()

if __name__=='__main__':
    App().mainloop()
