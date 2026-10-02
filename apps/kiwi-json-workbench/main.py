"""Inspect, transform, and list paths in a shared JSON workspace."""
import json,sys,threading,tkinter as tk
from pathlib import Path
from tkinter import ttk,filedialog,messagebox
sys.path.insert(0,str(Path(__file__).resolve().parent.parent/'common'))
import runtime,advanced
from workbench import App as BaseApp
from structured import fx_job,query_job,gron_job,tree_view

ENGINE_LABELS={'fx':'ツリー閲覧・JavaScript','gojq':'JSON式（jq形式）','gron':'パス一覧・復元'}

class App(BaseApp):
    def __init__(self,source_dir,native_paths=None):
        source_dir=Path(source_dir)
        self.engine='fx';self.states={};self.profiles={}
        for engine in ENGINE_LABELS:
            p=Path(runtime.resource_path(f'profiles/{engine}/profile.json',source_dir))
            self.profiles[engine]=json.loads(p.read_text(encoding='utf8'))
            self.profiles[engine]['title']='きういJSON作業場'
        self.native_paths={e:str((native_paths or {}).get(e,runtime.resource_path(p['tool'],source_dir))) for e,p in self.profiles.items()}
        super().__init__(self.profiles['fx'],source_dir)
        self.exe_path=self.native_paths['fx'];self.root.geometry('1140x900')

    def _build_ui(self):
        row=ttk.Frame(self.root);row.pack(fill='x',padx=5,pady=3)
        ttk.Label(row,text='用途:').pack(side='left')
        self.engine_combo=ttk.Combobox(row,values=list(ENGINE_LABELS.values()),state='readonly',width=34)
        self.engine_combo.set(ENGINE_LABELS[self.engine]);self.engine_combo.pack(side='left',padx=5)
        self.engine_combo.bind('<<ComboboxSelected>>',lambda event:self.switch_engine(next(e for e,l in ENGINE_LABELS.items() if l==self.engine_combo.get())))
        super()._build_ui()
        widgets=list(self.root.winfo_children())
        while widgets:
            w=widgets.pop();widgets.extend(w.winfo_children())
            if isinstance(w,ttk.Button) and w.cget('text')=='フォルダーを追加':w.configure(state='disabled')
        row=ttk.Frame(self.root);row.pack(fill='x',padx=5,pady=3)
        for label,callback in [('デモを入力',self.demo),('結果をツリーで開く',self.open_tree),('結果を入力へ',self.result_to_input),('色なしで保存',self.save_plain)]:
            ttk.Button(row,text=label,command=callback).pack(side='left',padx=2)
        presets={'fx':[('項目名','keys'),('値の一覧','values'),('件数','len'),('並べ替え','sort'),('重複除去','uniq')],'gojq':[('整形','.'),('件数','length'),('項目名','keys'),('各要素','.[]'),('並べ替え','sort'),('重複除去','unique')]}.get(self.engine,[])
        row=ttk.Frame(self.root);row.pack(fill='x',padx=5,pady=2)
        for label,query in presets:ttk.Button(row,text=label,command=lambda q=query:self.apply_preset(q)).pack(side='left',padx=2)

    def _attach_advanced(self):
        prefix=f'profiles/{self.engine}/'
        spec=json.loads(Path(runtime.resource_path(prefix+'advanced-spec.json',self.source_dir)).read_text(encoding='utf8'))
        controller=advanced.AdvancedController(self.root,self.profile['tool'],prefix+'upstream-help.txt',spec,self.source_dir)
        controller.exe_path=self.native_paths[self.engine]
        return controller

    def apply_preset(self,query):
        self.mode_var.set(next(m['label'] for m in self.profile['modes'] if m['id']=='query'))
        if '@stages' in self.repeat_widgets:
            w=self.repeat_widgets['@stages'];w.delete('1.0','end');w.insert('1.0',query)
        elif '@filter' in self.values:self.values['@filter'].set(query)

    def demo(self):
        self._clear_paths();self.in_text.delete('1.0','end')
        self.in_text.insert('1.0','{"items":[{"name":"coffee","price":180},{"name":"tea","price":150}]}')
        if '@url' in self.values:self.values['@url'].set('')
        if '@input' in self.values:self.values['@input'].set('json')
        self.mode_var.set(self.profile['modes'][0]['label'])
        if self.engine=='gojq':self.values['@filter'].set('.')

    def _busy(self):
        detail=self.advanced
        return bool((self.worker and self.worker.is_alive()) or str(self.run_btn.cget('state'))=='disabled' or detail.running or (detail.worker_thread and detail.worker_thread.is_alive()))

    def run(self):
        if self._busy():return
        mode=next(m['id'] for m in self.profile['modes'] if m['label']==self.mode_var.get())
        values={k:v.get() for k,v in self.values.items()}
        values.update({k:w.get('1.0','end-1c') for k,w in self.repeat_widgets.items()})
        engine=self.engine;exe=self.exe_path;paths=list(self.paths);text=self.in_text.get('1.0','end-1c')
        self.cancel_event.clear();self.last_result=None;self.status_var.set('実行中…')
        self.run_btn.config(state='disabled');self.stop_btn.config(state='normal')
        self.worker=threading.Thread(target=self._job,args=(engine,exe,mode,values,paths,text),daemon=True);self.worker.start()

    def _job(self,engine,exe,mode,values,paths,text):
        try:
            execute={'fx':fx_job.execute_job,'gojq':query_job.execute_job,'gron':gron_job.execute_job}[engine]
            result=execute(exe,mode,values,paths,text,self.cancel_event)
            result.update(engine=engine,mode=mode,tree_input=engine=='fx' and mode=='tree')
            success=result['returncode'] in ((0,1,4) if engine=='gojq' else (0,))
            self.q.put(('done',result['returncode'],result['stdout'],result['stderr'],success,result))
        except InterruptedError:self.q.put(('error','処理を停止しました。'))
        except TimeoutError:self.q.put(('error','時間制限に達したため停止しました。'))
        except Exception as error:self.q.put(('error',str(error)))

    def save_plain(self):
        if not self.last_result or 'stdout' not in self.last_result:return
        try:text=runtime._strip_ansi(self.last_result['stdout'].decode('utf8'))
        except UnicodeError:
            messagebox.showerror('保存','UTF-8として読めません。「結果を保存」で原文を保存できます。');return
        filename=filedialog.asksaveasfilename(defaultextension=self.last_result.get('extension','.txt'))
        if not filename:return
        if Path(filename).exists() and not messagebox.askyesno('確認','ファイルが存在します。上書きしますか？'):return
        try:Path(filename).write_text(text,encoding='utf8',newline='')
        except OSError as error:messagebox.showerror('保存',str(error))

    def switch_engine(self,target):
        if target==self.engine:return
        if target not in self.profiles:raise ValueError('未対応の用途です。')
        if self._busy():
            self.engine_combo.set(ENGINE_LABELS[self.engine]);messagebox.showwarning('用途','処理が終わるか停止してから切り替えてください。');return
        shared=(self.in_text.get('1.0','end-1c'),self.out_text.get('1.0','end-1c'),list(self.paths),self.last_result)
        self.states[self.engine]={'mode':self.mode_var.get(),'values':{k:v.get() for k,v in self.values.items()},'repeat':{k:w.get('1.0','end-1c') for k,w in self.repeat_widgets.items()}}
        self.root.after_cancel(self._poll_id)
        if self.advanced.toplevel:self.advanced._on_toplevel_close()
        self.root.config(menu='')
        for child in self.root.winfo_children():child.destroy()
        for attr in ('menubar','advanced_menu'):
            if hasattr(self.root,attr):delattr(self.root,attr)
        self.engine=target;self.profile=self.profiles[target];self.exe_path=self.native_paths[target]
        state=self.states.get(target,{})
        self.mode_var=tk.StringVar(master=self.root,value=state.get('mode',self.profile['modes'][0]['label']))
        self.values={}
        for field in self.profile['fields']:
            value=state.get('values',{}).get(field['flag'],field.get('default',''))
            cls=tk.BooleanVar if field['type']=='bool' else tk.StringVar
            self.values[field['flag']]=cls(master=self.root,value=value)
        self.repeat_widgets={};self._build_ui()
        self.in_text.insert('1.0',shared[0]);self.out_text.configure(state='normal')
        self.out_text.insert('1.0',shared[1]);self.out_text.configure(state='disabled')
        self.paths=shared[2];self.last_result=shared[3]
        for path in self.paths:self.path_list.insert('end',path)
        for name,text in state.get('repeat',{}).items():
            w=self.repeat_widgets[name];w.delete('1.0','end');w.insert('1.0',text)

    def open_tree(self):
        if not self.last_result or 'stdout' not in self.last_result:
            messagebox.showinfo('ツリー','先にデータを読み込むか、式を実行してください。');return
        try:
            data=runtime._strip_ansi(self.last_result['stdout'].decode('utf8')).encode('utf8')
            if self.last_result.get('tree_input'):
                roots=tree_view.parse_documents(data)
                if len(roots)!=1 or not isinstance(roots[0],list):raise ValueError('ツリー用データを読めません。')
                data='\n'.join(tree_view.dump_json(v) for v in roots[0]).encode('utf8')
            self.tree_window=tree_view.TreeWindow(self.root,data)
        except (ValueError,RecursionError,UnicodeError) as error:messagebox.showerror('ツリーを開けません',str(error))

    def result_to_input(self):
        if not self.last_result or 'stdout' not in self.last_result:return
        try:
            text=self.last_result['stdout'].decode('utf8')
            if '\x00' in text:raise ValueError('NUL文字を含む出力は入力欄へ移せません。原文を保存してください。')
            text=runtime._strip_ansi(text)
            if len(text.encode('utf8'))>2*1024*1024:raise ValueError('入力欄は2 MiBまでです。原文を保存してファイルで指定できます。')
        except (UnicodeError,ValueError) as error:
            messagebox.showerror('入力への移送',str(error));return
        self._clear_paths()
        if '@url' in self.values:self.values['@url'].set('')
        self.in_text.delete('1.0','end');self.in_text.insert('1.0',text)

if __name__=='__main__':App(Path(__file__).resolve().parent).root.mainloop()
