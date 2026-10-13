"""Generate a regular expression and use it for previewed text replacement."""
import sys,json,threading,queue,tkinter as tk
from pathlib import Path
from tkinter import ttk,messagebox
sys.path.insert(0,str(Path(__file__).resolve().parent.parent/'common'))
import replace_view,regex_core,runtime,advanced
from queue import Empty

class App(replace_view.ReplaceApp):
    def __init__(self,profile,source_dir):
        self._pattern_queue=queue.Queue();self._pattern_thread=None;self._grex_cancel_event=threading.Event()
        self._pattern_busy=False;self._closing=False;self._grex_detail=None
        super().__init__(profile,source_dir)
        self.root.title('きういテキスト作業場');self.root.geometry('1140x1000');self.root.minsize(900,850)
        prefix='profiles/grex/'
        spec=json.loads(Path(runtime.resource_path(prefix+'advanced-spec.json',source_dir)).read_text(encoding='utf8'))
        self._grex_detail=advanced.AdvancedController(self.root,'grex.exe',prefix+'upstream-help.txt',spec,source_dir)
        self.root.advanced_menu.delete(0,'end')
        for label,c in [('正規表現生成（grex）',self._grex_detail),('置換（sd）',self.advanced)]:
            self.root.advanced_menu.add_command(label=label,command=c.open_window)
            original=c._run
            c._run=lambda method=original:method() if not self._is_busy() else self.status_var.set('実行中の処理が終わるまでお待ちください。')
        self.root.protocol('WM_DELETE_WINDOW',self._on_close)
        self._poll_pattern_queue()

    def _build_ui(self):
        super()._build_ui()
        first=self.root.winfo_children()[0]
        upper=ttk.LabelFrame(self.root,text='例から正規表現を作る',padding=6);upper.pack(fill='x',padx=5,pady=4,before=first)
        row=ttk.Frame(upper);row.pack(fill='x')
        self.examples_text=tk.Text(row,height=3,width=60,wrap='none');self.examples_text.pack(side='left',fill='x',expand=True)
        opts=ttk.Frame(row);opts.pack(side='right',padx=8)
        self.digits_var=tk.BooleanVar(value=False);self.ignorecase_var=tk.BooleanVar(value=False);self.repetitions_var=tk.BooleanVar(value=True)
        for label,var in [('数字を一般化',self.digits_var),('大小文字を無視',self.ignorecase_var),('繰り返しを検出',self.repetitions_var)]:ttk.Checkbutton(opts,text=label,variable=var).pack(anchor='w')
        self.pattern_var=tk.StringVar();row=ttk.Frame(upper);row.pack(fill='x',pady=4)
        ttk.Label(row,text='生成した式:').pack(side='left')
        self.pattern_entry=ttk.Entry(row,textvariable=self.pattern_var,state='readonly');self.pattern_entry.pack(side='left',fill='x',expand=True,padx=4)
        ttk.Button(row,text='式をコピー',command=self._copy_pattern).pack(side='left')
        row=ttk.Frame(upper);row.pack(fill='x')
        self.grex_gen_btn=ttk.Button(row,text='正規表現を生成',command=self._generate_grex);self.grex_gen_btn.pack(side='left')
        self.transfer_btn=ttk.Button(row,text='検索欄へ渡す',state='disabled',command=self._transfer_pattern);self.transfer_btn.pack(side='left',padx=4)
        ttk.Label(row,text='渡した式の ^ と $ は行の始まり・終わりに一致します。').pack(side='left',padx=5)
        self.grex_status_var=tk.StringVar(value='例を1行ずつ入力してください。');ttk.Label(upper,textvariable=self.grex_status_var).pack(anchor='w')
        self.examples_text.bind('<<Modified>>',self._on_examples_modified)

    def _on_examples_modified(self,event=None):
        if not self.examples_text.edit_modified():return
        self.examples_text.edit_modified(False)
        if not self._pattern_busy:
            self.pattern_var.set('');self.transfer_btn.config(state='disabled');self.grex_status_var.set('例を変更しました。式を生成し直してください。')

    def _copy_pattern(self):
        if self._is_busy() or not self.pattern_var.get():return
        self.root.clipboard_clear();self.root.clipboard_append(self.pattern_var.get())

    def run(self):
        if self._is_busy():return
        super().run()

    def _stop(self):
        self._grex_cancel_event.set();super()._stop()

    def _poll_queue(self):
        super()._poll_queue()
        if self._pattern_busy:self.stop_btn.config(state='normal')

    def _on_close(self):
        self._closing=True;self.cancel_event.set();self._grex_cancel_event.set()
        controllers=[c for c in (getattr(self,'advanced',None),self._grex_detail) if c]
        for c in controllers:c.cancel_event.set()
        threads=[self.worker,self._pattern_thread,*(c.worker_thread for c in controllers)]
        if any(t and t.is_alive() for t in threads):self.root.after(50,self._on_close);return
        for timer in self.root.tk.splitlist(self.root.tk.call('after','info')):self.root.after_cancel(timer)
        self.root.destroy()

    def _is_busy(self):
        if self._closing:return True
        if self._pattern_busy:
            return True
        if str(self.run_btn['state']) == 'disabled':
            return True
        if self.worker and self.worker.is_alive():
            return True
        adv = getattr(self, 'advanced', None)
        if adv is not None and (getattr(adv, 'running', False) or (getattr(adv, 'worker_thread', None) and adv.worker_thread.is_alive())):
            return True
        det = getattr(self, '_grex_detail', None)
        if det is not None and (getattr(det, 'running', False) or (getattr(det, 'worker_thread', None) and det.worker_thread.is_alive())):
            return True
        return False

    def _generate_grex(self):
        if self._is_busy():
            return
        raw = self.examples_text.get('1.0', 'end-1c')
        try:
            examples = regex_core.validated_examples(raw)
        except Exception as e:
            self.grex_status_var.set(f"エラー: {regex_core._sanitize_error(e)}")
            return
        if not examples:
            self.grex_status_var.set("エラー: 有効な例がありません")
            return

        digits = bool(self.digits_var.get())
        ignorecase = bool(self.ignorecase_var.get())
        repetitions = bool(self.repetitions_var.get())
        exe = Path(runtime.resource_path('grex.exe', self.source_dir))

        self._grex_cancel_event.clear();self._pattern_busy = True
        self.examples_text.config(state='disabled')
        self.grex_gen_btn.config(state='disabled')
        self.transfer_btn.config(state='disabled')
        self.stop_btn.config(state='normal')
        self.grex_status_var.set("生成中...")

        def _worker():
            try:
                result = regex_core._run_grex(exe, examples, digits, ignorecase, repetitions, self._grex_cancel_event)
                self._pattern_queue.put(('result', str(result)))
            except Exception as e:
                self._pattern_queue.put(('error', regex_core._sanitize_error(e)))

        self._pattern_thread = threading.Thread(target=_worker, daemon=True)
        self._pattern_thread.start()

    def _poll_pattern_queue(self):
        if self._closing:
            return
        try:
            while True:
                item = self._pattern_queue.get_nowait()
                kind, payload = item[0], item[1]
                if kind == 'result':
                    self.pattern_var.set(payload)
                    self.grex_status_var.set("生成完了")
                    self.transfer_btn.config(state='normal')
                elif kind == 'error':
                    old = self.pattern_var.get()
                    self.grex_status_var.set(f"エラー: {payload}")
                    if old:
                        self.transfer_btn.config(state='normal')
        except queue.Empty:
            pass

        if self._pattern_busy and (self._pattern_thread is None or not self._pattern_thread.is_alive()):
            self._pattern_busy = False
            self.examples_text.config(state='normal')
            self.grex_gen_btn.config(state='normal')
            self.stop_btn.config(state='disabled')

        if not self._closing:
            self.root.after(50, self._poll_pattern_queue)

    def _transfer_pattern(self):
        if self._is_busy():
            return
        pattern = self.pattern_var.get().strip()
        if not pattern:
            return
        self.values['find'].set(pattern)
        self.values['--fixed-strings'].set(False)
        self.values['flag-m'].set(True)
        self.values['flag-e'].set(False)

if __name__=='__main__':
    source=Path(__file__).resolve().parent
    profile=json.loads(Path(runtime.resource_path('profile.json',source)).read_text(encoding='utf8'))
    App(profile,source).root.mainloop()
