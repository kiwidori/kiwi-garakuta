"""View source, format shell text, and assemble readable code documents."""
import json,sys,threading,tkinter as tk
from pathlib import Path
from tkinter import ttk,filedialog,messagebox
sys.path.insert(0,str(Path(__file__).resolve().parent.parent/'common'))
import runtime,advanced,job,transfer
from workbench import App as BaseApp
from ansi_renderer import render_ansi

LABELS={'bat':'コード閲覧','shfmt':'シェル整形','code2prompt':'コード資料','glow':'Markdown閲覧'}

class App(BaseApp):
    def __init__(self,source_dir,native_paths=None):
        self.engine='bat';self.source_dir=Path(source_dir);self.states={};self.profiles={};self._closing=False;self._rendered=None
        for e in LABELS:
            p=Path(runtime.resource_path('profiles/'+e+'/profile.json',self.source_dir))
            self.profiles[e]=json.loads(p.read_text(encoding='utf8'))
            self.profiles[e]['title']='きういコード・文書作業場'
        self.native_paths={e:str((native_paths or {}).get(e,runtime.resource_path(p['tool'],self.source_dir))) for e,p in self.profiles.items()}
        super().__init__(self.profiles[self.engine],self.source_dir)
        self.exe_path=self.native_paths[self.engine];self.root.geometry('1160x900');self.root.minsize(960,760)

    def _build_ui(self):
        top=ttk.Frame(self.root);top.pack(fill='x',padx=5,pady=3)
        ttk.Label(top,text='用途:').pack(side='left')
        self.engine_combo=ttk.Combobox(top,values=list(LABELS.values()),state='readonly',width=20)
        self.engine_combo.set(LABELS[self.engine]);self.engine_combo.pack(side='left',padx=4)
        self.engine_combo.bind('<<ComboboxSelected>>',lambda event:self.switch_engine(next(e for e,l in LABELS.items() if l==self.engine_combo.get())))
        ttk.Button(top,text='整形結果をコード閲覧へ',command=lambda:self.send_result('bat')).pack(side='left',padx=3)
        ttk.Button(top,text='生成資料をMarkdown閲覧へ',command=lambda:self.send_result('glow')).pack(side='left',padx=3)
        ttk.Button(top,text='ファイルのフォルダーを資料対象へ',command=self.folder_to_prompt).pack(side='left',padx=3)
        super()._build_ui()
        self.tabs.pack_configure(expand=False)
        for tab in self.tabs.tabs():
            for w in self.tabs.nametowidget(tab).winfo_children():
                if isinstance(w,tk.Canvas):w.configure(height=190)
        self.in_text.master.configure(text='共有テキスト（コード資料では使いません。ファイル指定時は空欄）')
        self.out_text.configure(font=('Consolas',10),wrap='none')
        sb=ttk.Scrollbar(self.out_text.master,orient='horizontal',command=self.out_text.xview)
        sb.pack(side='bottom',fill='x');self.out_text.configure(xscrollcommand=sb.set)
        ctrl=self.run_btn.master
        ttk.Button(ctrl,text='結果をコピー',command=self.copy_result).pack(side='left',padx=2)
        if self.engine=='bat':
            for label,offset in [('前の500行',-500),('次の500行',500)]:ttk.Button(ctrl,text=label,command=lambda n=offset:self.page(n)).pack(side='left',padx=2)
            ttk.Button(ctrl,text='装飾を除いて保存',command=self.save_plain).pack(side='left',padx=2)
        if self.engine=='glow':
            ttk.Button(ctrl,text='装飾を除いて保存',command=self.save_plain).pack(side='left',padx=2)
            ttk.Button(ctrl,text='スタイル選択(JSON)',command=self.choose_style).pack(side='left',padx=2)
            row=ttk.Frame(self.root);row.pack(fill='x',padx=5)
            ttk.Label(row,text='テーマ:').pack(side='left')
            for name in ('light','dark','ascii','tokyo-night','notty'):ttk.Button(row,text=name,command=lambda n=name:self.set_theme(n)).pack(side='left',padx=2)
        if self.engine=='code2prompt':
            ttk.Button(ctrl,text='テンプレートを選択',command=self.choose_template).pack(side='left',padx=2)
            ttk.Button(ctrl,text='診断・トークン情報を保存',command=self.save_diagnostics).pack(side='left',padx=2)
            self.path_list.master.configure(text='資料にまとめるフォルダーを1つ選択（共有テキストは使いません）')
        ttk.Label(self.root,text='切替・移送では実行しません。元ファイルは自動で変更せず、スクリプトも実行しません。').pack(anchor='w',padx=5,pady=2)

    def _attach_advanced(self):
        prefix='profiles/'+self.engine+'/'
        spec=json.loads(Path(runtime.resource_path(prefix+'advanced-spec.json',self.source_dir)).read_text(encoding='utf8'))
        c=advanced.AdvancedController(self.root,self.profile['tool'],prefix+'upstream-help.txt',spec,self.source_dir)
        c.exe_path=self.native_paths[self.engine];original=c._run
        c._run=lambda:original() if not self._busy() else self.status_var.set('処理が終わるまでお待ちください。')
        return c

    def _busy(self):
        c=getattr(self,'advanced',None)
        return self._closing or not self.q.empty() or bool(self.worker and self.worker.is_alive()) or str(self.run_btn.cget('state'))=='disabled' or bool(c and (c.running or not c.result_queue.empty() or (c.worker_thread and c.worker_thread.is_alive())))

    def run(self):
        if self._busy():return
        mode=next((m for m in self.profile['modes'] if m['label']==self.mode_var.get()),None)
        if mode is None:return
        values={k:v.get() for k,v in self.values.items()};values.update({k:w.get('1.0','end-1c') for k,w in self.repeat_widgets.items()})
        args=(self.engine,self.exe_path,self.profile,dict(mode),values,list(self.paths),self.in_text.get('1.0','end-1c'))
        self.cancel_event.clear();self.last_result=None;self._rendered=None
        self.run_btn.configure(state='disabled');self.stop_btn.configure(state='normal');self.status_var.set('実行中…')
        self.out_text.configure(state='normal');self.out_text.delete('1.0','end');self.out_text.configure(state='disabled')
        self.worker=threading.Thread(target=self._job,args=args,daemon=True);self.worker.start()

    def _job(self,engine,exe,profile,mode,values,paths,text):
        try:
            r=job.execute(engine,exe,profile,mode,values,paths,text,self.cancel_event);rc=r['returncode']
            r['theme']=values.get('--theme') if engine=='bat' else values.get('--style')
            self.q.put(('done',rc,r['stdout'],r['stderr'],rc in mode.get('success_codes',[0]),r))
        except InterruptedError:self.q.put(('error','処理を停止しました。'))
        except TimeoutError:self.q.put(('error','時間制限に達したため停止しました。'))
        except Exception as error:self.q.put(('error',str(error)))

    def _poll_queue(self):
        super()._poll_queue()
        r=self.last_result
        if r and 'stdout' in r and r is not self._rendered:
            self._rendered=r
            if r.get('engine') in ('bat','glow','code2prompt'):
                dark=r.get('engine')=='code2prompt' or r.get('theme') in ('TwoDark','Dracula','dark','tokyo-night')
                self.out_text.configure(background='#282c34' if dark else '#ffffff',foreground='#f8fafc' if dark else '#24292f')
                text=r['stdout'].decode('utf8','replace')
                if r.get('stderr'):text+='\n--- 診断（標準エラー） ---\n'+r['stderr'].decode('utf8','replace')
                render_ansi(self.out_text,text,max_bytes=2*1024*1024 if r.get('engine')=='bat' else 128*1024)
            if r.get('engine')=='shfmt' and r.get('returncode')==1:self.status_var.set('差分があります。結果を保存できます。')

    def switch_engine(self,target):
        if target not in self.profiles:raise ValueError('未対応の用途です。')
        if target==self.engine:return True
        if self._busy():
            self.engine_combo.set(LABELS[self.engine]);self.status_var.set('処理が終わるか停止してから切り替えてください。');return False
        shared=(self.in_text.get('1.0','end-1c'),self.out_text.get('1.0','end-1c'),list(self.paths),self.last_result)
        self.states[self.engine]={'mode':self.mode_var.get(),'values':{k:v.get() for k,v in self.values.items()},'repeat':{k:w.get('1.0','end-1c') for k,w in self.repeat_widgets.items()}}
        self.root.after_cancel(self._poll_id)
        if self.advanced.toplevel:self.advanced._on_toplevel_close()
        self.root.configure(menu='')
        for child in self.root.winfo_children():child.destroy()
        for name in ('menubar','advanced_menu'):
            if hasattr(self.root,name):delattr(self.root,name)
        self.engine=target;self.profile=self.profiles[target];self.exe_path=self.native_paths[target]
        state=self.states.get(target,{})
        self.mode_var=tk.StringVar(master=self.root,value=state.get('mode',self.profile['modes'][0]['label']))
        self.values={}
        for f in self.profile['fields']:
            cls=tk.BooleanVar if f['type']=='bool' else tk.StringVar
            self.values[f['flag']]=cls(master=self.root,value=state.get('values',{}).get(f['flag'],f.get('default',False if f['type']=='bool' else '')))
        self.repeat_widgets={};self._build_ui()
        self.in_text.insert('1.0',shared[0]);self.out_text.configure(state='normal');self.out_text.insert('1.0',shared[1]);self.out_text.configure(state='disabled')
        self.paths=shared[2];self.last_result=shared[3]
        for p in self.paths:self.path_list.insert('end',p)
        for k,t in state.get('repeat',{}).items():self.repeat_widgets[k].delete('1.0','end');self.repeat_widgets[k].insert('1.0',t)
        if self.engine=='glow':self.set_theme(self.values['--style'].get())
        self.status_var.set('用途を切り替えました。入力を確認して実行してください。');return True

    def send_result(self,target):
        if self._busy():return
        try:text=transfer.payload(self.last_result,target)
        except ValueError as error:messagebox.showinfo('結果の移送',str(error));return
        old=self.in_text.get('1.0','end-1c')
        if (old and old!=text or self.paths) and not messagebox.askyesno('結果の移送','共有入力と対象ファイル指定を、この結果で置き換えますか？'):return
        if not self.switch_engine(target):return
        self._clear_paths();self.in_text.delete('1.0','end');self.in_text.insert('1.0',text)
        self.mode_var.set(self.profile['modes'][0]['label'])
        if target=='bat':self.values['@first'].set('1');self.values['--language'].set('sh')
        self.status_var.set('結果を入力へ移しました。「実行」で表示できます。')

    def folder_to_prompt(self):
        if self._busy():return
        if len(self.paths)!=1:messagebox.showinfo('資料の対象','ファイルまたはフォルダーを1つ選択してください。');return
        try:
            p=Path(job.validate_path(self.paths[0]));p=p if p.is_dir() else p.parent
            job.validate_path(p)
        except (ValueError,OSError) as error:messagebox.showerror('資料の対象',str(error));return
        if not messagebox.askyesno('資料の対象','次のフォルダーを資料の対象にしますか？\n'+str(p)+'\nまだ生成しません。'):return
        if not self.switch_engine('code2prompt'):return
        self._clear_paths();self.paths=[str(p)];self.path_list.insert('end',str(p));self.mode_var.set('コード資料を生成')

    def page(self,offset):
        if self._busy():return
        try:n=int(self.values['@first'].get())
        except ValueError:n=1
        self.values['@first'].set(str(max(1,n+offset)));self.run()

    def choose_template(self):
        if self._busy():return
        p=filedialog.askopenfilename(filetypes=[('Handlebars','*.hbs *.handlebars'),('すべて','*.*')])
        if p:self.values['--template'].set(p)

    def choose_style(self):
        if self._busy():return
        p=filedialog.askopenfilename(filetypes=[('JSON','*.json')])
        if p:self.values['--style'].set(p)

    def set_theme(self,name):
        self.values['--style'].set(name)
        dark=name in ('dark','tokyo-night')
        self.out_text.configure(background='#1e1e2e' if dark else '#ffffff',foreground='#ffffff' if dark else '#000000')

    def copy_result(self):
        if self._busy() or not self.last_result or 'stdout' not in self.last_result:return
        if self.last_result.get('extension')=='.zip':messagebox.showinfo('コピー','ZIPはファイルとして保存してください。');return
        try:
            text=self.last_result['stdout'].decode('utf8')
            if self.last_result.get('engine') in ('bat','glow'):text=runtime._strip_ansi(text)
            self.root.clipboard_clear();self.root.clipboard_append(text);self.root.update_idletasks();self.status_var.set('結果をコピーしました。')
        except (UnicodeError,tk.TclError) as error:messagebox.showerror('コピー',str(error))

    def save_plain(self):
        if self._busy() or not self.last_result or 'stdout' not in self.last_result:return
        name=filedialog.asksaveasfilename(defaultextension='.txt',confirmoverwrite=True)
        if name:
            try:Path(name).write_text(runtime._strip_ansi(self.last_result['stdout'].decode('utf8')),encoding='utf8',newline='')
            except (OSError,UnicodeError) as error:messagebox.showerror('保存',str(error))

    def save_diagnostics(self):
        if self._busy() or not self.last_result:return
        name=filedialog.asksaveasfilename(defaultextension='.log',confirmoverwrite=True)
        if name:
            try:Path(name).write_bytes(self.last_result.get('stderr',b''))
            except OSError as error:messagebox.showerror('保存',str(error))

    def _on_close(self):
        self._closing=True;super()._on_close()

if __name__=='__main__':App(Path(__file__).resolve().parent).root.mainloop()
