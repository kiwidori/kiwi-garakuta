"""Inspect JSON paths with the bundled gron executable."""
import sys,json,threading
from pathlib import Path
from tkinter import ttk,filedialog,messagebox
sys.path.insert(0,str(Path(__file__).resolve().parent.parent/'common'))
import runtime
from workbench import App as BaseApp
from gron_job import build_request,execute_job

class App(BaseApp):
    def _build_ui(self):
        super()._build_ui()
        def all_widgets(parent):
            for child in parent.winfo_children():
                yield child;yield from all_widgets(child)
        for widget in all_widgets(self.root):
            if isinstance(widget,ttk.Button):
                if widget.cget('text')=='フォルダーを追加':widget.pack_forget()
                if widget.cget('text')=='結果を保存':widget.configure(text='原文を保存')
        row=ttk.Frame(self.root);row.pack(fill='x',padx=5,pady=3)
        ttk.Button(row,text='色なしで保存',command=self.save_plain).pack(side='left',padx=3)
        ttk.Button(row,text='結果を入力へ',command=self.result_to_input).pack(side='left',padx=3)
        ttk.Label(row,text='値の抽出では、配列の添字や引用符付きのキーも含まれる場合があります。').pack(side='left',padx=10)
        self.root.geometry('1120x850')
    def result_to_input(self):
        if not self.last_result or 'stdout' not in self.last_result:return
        text=runtime._strip_ansi(self.last_result['stdout'].decode('utf8','replace'))
        if len(text.encode('utf8'))>2*1024*1024:messagebox.showerror('入力','入力欄は2 MiBまでです。原文を保存してファイルで指定できます。');return
        self.in_text.delete('1.0','end');self.in_text.insert('1.0',text);self._clear_paths();self.values['@url'].set('')
    def save_plain(self):
        if not self.last_result or 'stdout' not in self.last_result:return
        path=filedialog.asksaveasfilename(defaultextension=self.last_result.get('extension','.txt'))
        if path:
            try:Path(path).write_text(runtime._strip_ansi(self.last_result['stdout'].decode('utf8','replace')),encoding='utf8',newline='')
            except OSError as e:messagebox.showerror('保存',str(e))
    def run(self):
        if self.worker and self.worker.is_alive():return
        mode=next(m['id'] for m in self.profile['modes'] if m['label']==self.mode_var.get())
        values={k:v.get() for k,v in self.values.items()};paths=list(self.paths);text=self.in_text.get('1.0','end-1c')
        self.cancel_event.clear();self.last_result=None;self.status_var.set('実行中…')
        self.run_btn.config(state='disabled');self.stop_btn.config(state='normal')
        self.worker=threading.Thread(target=self._job,args=(mode,values,paths,text),daemon=True);self.worker.start()
    def _job(self,mode,values,paths,text):
        try:
            r=execute_job(self.exe_path,mode,values,paths,text,self.cancel_event)
            self.q.put(('done',r['returncode'],r['stdout'],r['stderr'],r['returncode']==0,r))
        except Exception as e:self.q.put(('error',str(e)))

if __name__=='__main__':
    source=Path(__file__).resolve().parent
    profile=json.loads(Path(runtime.resource_path('profile.json',source)).read_text(encoding='utf8'))
    App(profile,source).root.mainloop()
