"""Evaluate JSON and YAML queries with the bundled gojq."""
import sys,json,threading
from pathlib import Path
from tkinter import ttk,filedialog,messagebox
sys.path.insert(0,str(Path(__file__).resolve().parent.parent/'common'))
import runtime
from workbench import App as BaseApp
from query_job import execute_job

class App(BaseApp):
    def _build_ui(self):
        super()._build_ui()
        widgets=list(self.root.winfo_children())
        while widgets:
            widget=widgets.pop();widgets.extend(widget.winfo_children())
            if isinstance(widget,ttk.Button) and widget.cget("text")=="フォルダーを追加":widget.configure(state="disabled")
        row=ttk.Frame(self.root);row.pack(pady=3)
        for label,query in [('整形','.'),('配列の件数','length'),('項目名','keys'),('値の一覧','.[]'),('並べ替え','sort'),('重複除去','unique')]:
            ttk.Button(row,text=label,command=lambda q=query:self.values['@filter'].set(q)).pack(side='left',padx=2)

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
            self.q.put(('done',r['returncode'],r['stdout'],r['stderr'],r['returncode'] in (0,1,4),r))
        except Exception as e:self.q.put(('error',str(e)))

if __name__=='__main__':
    source=Path(__file__).resolve().parent
    profile=json.loads(Path(runtime.resource_path('profile.json',source)).read_text(encoding='utf8'))
    App(profile,source).root.mainloop()
