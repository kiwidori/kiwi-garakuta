"""YAML formatting, checks and reports using the bundled yamlfmt CLI."""
import os,sys,json,threading
from pathlib import Path
import tkinter as tk
from tkinter import ttk,filedialog,messagebox
import yaml
sys.path.insert(0,str(Path(__file__).resolve().parent.parent/'common'))
import runtime
from workbench import App as BaseApp
from yamlfmt_job import execute_job

def parse_settings(text,values,profile):
    if len(text.encode('utf8'))>128*1024:raise ValueError('設定は128 KiBまでです。')
    config=yaml.safe_load(text) or {}
    if not isinstance(config,dict):raise ValueError('設定はキーと値の形式で指定してください。')
    formatter=config.get('formatter',{}) or {}
    if not isinstance(formatter,dict):raise ValueError('formatterはキーと値の形式で指定してください。')
    formatter=dict(formatter)
    if values.get('@formatter'):
        if values['@formatter']!=formatter.get('type','basic'):formatter={}
        formatter['type']=values['@formatter']
    overrides={k[3:]:v for k,v in values.items() if k.startswith('@f.') and v!=''}
    if formatter.get('type','basic')=='kyaml' and overrides:
        raise ValueError('KYAMLではBasicの整形設定を空欄にしてください。')
    for k,v in overrides.items():
        if k in ('indent','array_indent','max_line_length','pad_line_comments'):
            if not str(v).isdigit() or int(v)>10000:raise ValueError('数値設定は0〜10000の整数で指定してください。')
            v=int(v)
        elif v in ('true','false'):v=v=='true'
        formatter[k]=v
    if formatter:config['formatter']=formatter
    if values.get('@line_ending'):config['line_ending']=values['@line_ending']
    args=[]
    for f in profile['fields']:
        k=f['flag'];v=values.get(k,'')
        if k.startswith('@') or not v:continue
        if f['type']=='bool':args.append(k)
        elif f.get('repeat'):
            for line in str(v).splitlines():
                if line.strip():args.extend([k,line.strip()])
        else:args.extend([k,str(v)])
    return args,json.dumps(config,ensure_ascii=False,allow_nan=False)

class App(BaseApp):
    def _build_ui(self):
        super()._build_ui()
        frame=ttk.Frame(self.tabs);self.tabs.add(frame,text='設定ファイル')
        row=ttk.Frame(frame);row.pack(fill='x')
        for label,command in [('設定を読み込む',self.load_config),('グローバル設定を読み込む',self.load_global),('設定を保存',self.save_config)]:
            ttk.Button(row,text=label,command=command).pack(side='left',padx=3)
        ttk.Label(frame,text='YAML / JSONの設定。空欄の項目はこの設定を引き継ぎます。自動検索は行いません。').pack(anchor='w')
        self.config_text=tk.Text(frame,height=7,wrap='none');self.config_text.pack(fill='both',expand=True)
        self.config_text.insert('1.0','{}')
        self.root.geometry('1150x900')
    def read_config(self,path):
        p=Path(path)
        if p.stat().st_size>128*1024:raise ValueError('設定は128 KiBまでです。')
        text=p.read_text(encoding='utf-8-sig');parse_settings(text,{},self.profile)
        self.config_text.delete('1.0','end');self.config_text.insert('1.0',text)
    def load_config(self):
        path=filedialog.askopenfilename(filetypes=[('設定ファイル','*')])
        if path:
            try:self.read_config(path)
            except Exception as e:messagebox.showerror('設定',str(e))
    def load_global(self):
        folder=Path(os.environ.get('LOCALAPPDATA',''))/'yamlfmt'
        try:
            p=next((folder/n for n in ('.yamlfmt','yamlfmt.yml','yamlfmt.yaml','.yamlfmt.yaml','.yamlfmt.yml') if (folder/n).is_file()),None)
            if p is None:raise ValueError('グローバル設定が見つかりません。設定を読み込むボタンから指定できます。')
            self.read_config(p)
        except Exception as e:messagebox.showerror('設定',str(e))
    def values_snapshot(self):
        values={k:v.get() for k,v in self.values.items()}
        values.update({k:w.get('1.0','end-1c') for k,w in self.repeat_widgets.items()})
        return values
    def save_config(self):
        try:
            _,text=parse_settings(self.config_text.get('1.0','end-1c'),self.values_snapshot(),self.profile)
            path=filedialog.asksaveasfilename(initialfile='.yamlfmt',defaultextension='.yaml')
            if path:Path(path).write_text(text+'\n',encoding='utf8')
        except Exception as e:messagebox.showerror('設定',str(e))
    def run(self):
        if self.worker and self.worker.is_alive():return
        try:
            mode=next(m for m in self.profile['modes'] if m['label']==self.mode_var.get())
            values=self.values_snapshot();text=self.in_text.get('1.0','end-1c')
            args,config=parse_settings(self.config_text.get('1.0','end-1c'),values,self.profile)
            data=text.encode('utf8')
            if len(data)>2*1024*1024:raise ValueError('入力テキストは2 MiBまでです。')
        except Exception as e:messagebox.showerror('入力',str(e));return
        self.last_result=None;self.cancel_event.clear()
        self.run_btn.config(state='disabled');self.stop_btn.config(state='normal');self.status_var.set('実行中…')
        self.worker=threading.Thread(target=self._job,args=(args,data,mode,list(self.paths),config,values.get('@patterns','')),daemon=True)
        self.worker.start()
    def _job(self,args,data,mode,paths,config,patterns):
        try:
            r=execute_job(self.exe_path,args,data,self.cancel_event,mode['id'],paths,config,patterns)
            # Lint returns 1 both for differences and invalid YAML; preserve it as failure.
            self.q.put(('done',r['returncode'],r['stdout'],r['stderr'],r['returncode']==0 or r.get('status')=='differences',r))
        except Exception as e:self.q.put(('error',str(e)))
    def _poll_queue(self):
        super()._poll_queue()
        if self.last_result and self.last_result.get('status')=='differences':
            self.status_var.set('整形が必要な箇所があります（終了コード1）。レポートを保存できます。')

if __name__=='__main__':
    source=Path(__file__).resolve().parent
    profile=json.loads(Path(runtime.resource_path('profile.json',source)).read_text(encoding='utf8'))
    App(profile,source).root.mainloop()
