"""Browse structured data and apply JavaScript expressions with fx."""
import sys,json,threading
from pathlib import Path
from tkinter import ttk,filedialog,messagebox
sys.path.insert(0,str(Path(__file__).resolve().parent.parent/'common'))
import runtime
from workbench import App as BaseApp
from fx_job import execute_job
from tree_view import TreeWindow,parse_documents,dump_json

class App(BaseApp):
    def _build_ui(self):
        super()._build_ui()
        widgets=list(self.root.winfo_children())
        while widgets:
            widget=widgets.pop();widgets.extend(widget.winfo_children())
            if isinstance(widget,ttk.Button) and widget.cget("text")=="フォルダーを追加":widget.configure(state="disabled")
        row=ttk.Frame(self.root);row.pack(pady=3)
        ttk.Button(row,text='結果をツリーで開く',command=self.open_tree).pack(side='left',padx=2)
        ttk.Button(row,text='デモを入力',command=self.demo).pack(side='left',padx=2)
        for label,query in [('項目名','keys'),('値の一覧','values'),('件数','len'),('並べ替え','sort'),('重複除去','uniq')]:
            ttk.Button(row,text=label,command=lambda q=query:self.set_query(q)).pack(side='left',padx=2)

    def set_query(self,query):
        self.mode_var.set('式を実行');w=self.repeat_widgets['@stages'];w.delete('1.0','end');w.insert('1.0',query)
    def demo(self):
        self.paths.clear();self.path_list.delete(0,'end');self.in_text.delete('1.0','end')
        self.in_text.insert('1.0','{"name":"Kiwi","items":[{"name":"coffee","price":180,"available":true},{"name":"tea","price":150,"available":false}],"notes":"選択した値やパスをコピーできます。"}')
        self.values['@input'].set('json');self.mode_var.set('ツリー用JSONを読み込む')
    def open_tree(self):
        if not self.last_result or 'stdout' not in self.last_result:
            messagebox.showinfo('ツリー','先にデータを読み込むか、式を実行してください。');return
        try:
            data=self.last_result['stdout']
            if self.last_result.get('tree_input'):
                roots=parse_documents(data)
                if len(roots)!=1 or not isinstance(roots[0],list):raise ValueError('ツリー用データを読めません。')
                data='\n'.join(dump_json(v) for v in roots[0]).encode('utf8')
            self.tree_window=TreeWindow(self.root,data)
        except (ValueError,RecursionError,UnicodeError) as error:messagebox.showerror('ツリーを開けません',str(error))

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
            r['tree_input']=mode=='tree'
            self.q.put(('done',r['returncode'],r['stdout'],r['stderr'],r['returncode']==0,r))
        except Exception as e:self.q.put(('error',str(e)))

if __name__=='__main__':
    source=Path(__file__).resolve().parent
    profile=json.loads(Path(runtime.resource_path('profile.json',source)).read_text(encoding='utf8'))
    App(profile,source).root.mainloop()
