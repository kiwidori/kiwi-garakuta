"""Inspect GitHub Actions workflows with the bundled actionlint."""
import sys,json,threading
from pathlib import Path
from tkinter import ttk,filedialog,messagebox
sys.path.insert(0,str(Path(__file__).resolve().parent.parent/'common'))
import runtime
from workbench import App as BaseApp
from check_job import execute_job

class App(BaseApp):
    def _build_ui(self):
        super()._build_ui()
        config=self.repeat_widgets['@config'];config.configure(height=10,width=90)
        row=ttk.Frame(config.master);row.pack(side='left')
        ttk.Button(row,text='設定を読み込む',command=self.load_config).pack(pady=3)
        ttk.Button(row,text='設定を保存',command=self.save_config).pack(pady=3)
        ttk.Label(self.root,text='終了コード1は指摘あり。ワークフローは実行しません。外部チェッカーは指定した場合だけ呼び出します。').pack(pady=3)
    def load_config(self):
        path=filedialog.askopenfilename(filetypes=[('YAML','*.yaml *.yml'),('All','*.*')])
        if not path:return
        try:
            with open(path,'rb') as f:data=f.read(128*1024+1)
            if len(data)>128*1024:raise ValueError('設定は128 KiBまでです。')
            text=data.decode('utf-8-sig');w=self.repeat_widgets['@config'];w.delete('1.0','end');w.insert('1.0',text)
        except (OSError,UnicodeError,ValueError) as e:messagebox.showerror('設定',str(e))
    def save_config(self):
        path=filedialog.asksaveasfilename(defaultextension='.yaml')
        if path:
            try:Path(path).write_text(self.repeat_widgets['@config'].get('1.0','end-1c'),encoding='utf8',newline='')
            except OSError as e:messagebox.showerror('設定',str(e))
    def run(self):
        if self.worker and self.worker.is_alive():return
        mode=next(m['id'] for m in self.profile['modes'] if m['label']==self.mode_var.get())
        values={k:v.get() for k,v in self.values.items()}
        for key,w in self.repeat_widgets.items():values[key]=w.get('1.0','end-1c')
        paths=list(self.paths);text=self.in_text.get('1.0','end-1c')
        self.cancel_event.clear();self.last_result=None;self.status_var.set('実行中…')
        self.run_btn.config(state='disabled');self.stop_btn.config(state='normal')
        self.worker=threading.Thread(target=self._job,args=(mode,values,paths,text),daemon=True);self.worker.start()
    def _job(self,mode,values,paths,text):
        try:
            r=execute_job(self.exe_path,mode,values,paths,text,self.cancel_event)
            self.q.put(('done',r['returncode'],r['stdout'],r['stderr'],r['returncode'] in (0,1),r))
        except Exception as e:self.q.put(('error',str(e)))

if __name__=='__main__':
    source=Path(__file__).resolve().parent
    profile=json.loads(Path(runtime.resource_path('profile.json',source)).read_text(encoding='utf8'))
    App(profile,source).root.mainloop()
