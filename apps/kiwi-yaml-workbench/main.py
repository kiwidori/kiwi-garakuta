"""Transform YAML, format it, and inspect GitHub Actions workflows."""
import sys,json,threading,tkinter as tk
from pathlib import Path
from tkinter import ttk,messagebox,filedialog
sys.path.insert(0,str(Path(__file__).resolve().parent.parent/'common'))
import runtime,advanced,job,format_view
from workbench import App as BaseApp

LABELS={'yq':'変換・編集','yamlfmt':'整形・差分','actionlint':'Actions検査'}

class App(BaseApp):
    def __init__(self,source_dir,native_paths=None):
        self.engine='yq';self.source_dir=Path(source_dir);self.states={};self.profiles={};self._closing=False
        for engine in LABELS:
            p=Path(runtime.resource_path('profiles/'+engine+'/profile.json',self.source_dir))
            self.profiles[engine]=json.loads(p.read_text(encoding='utf8'));self.profiles[engine]['title']='きういYAML作業場'
        self.native_paths={e:str((native_paths or {}).get(e,runtime.resource_path(p['tool'],self.source_dir))) for e,p in self.profiles.items()}
        super().__init__(self.profiles['yq'],self.source_dir)
        self.exe_path=self.native_paths['yq'];self.root.geometry('1160x940');self.root.minsize(900,740)

    def _build_ui(self):
        row=ttk.Frame(self.root);row.pack(fill='x',padx=5,pady=3)
        ttk.Label(row,text='用途:').pack(side='left')
        self.engine_combo=ttk.Combobox(row,values=list(LABELS.values()),state='readonly',width=22)
        self.engine_combo.set(LABELS[self.engine]);self.engine_combo.pack(side='left',padx=5)
        self.engine_combo.bind('<<ComboboxSelected>>',lambda event:self.switch_engine(next(e for e,l in LABELS.items() if l==self.engine_combo.get())))
        ttk.Button(row,text='結果を入力へ',command=self.result_to_input).pack(side='left',padx=5)
        super()._build_ui()
        self.tabs.pack_configure(expand=False)
        for tab in self.tabs.tabs():
            canvas=next((c for c in self.tabs.nametowidget(tab).winfo_children() if isinstance(c,tk.Canvas)),None)
            if canvas:canvas.configure(height=190)
        if self.engine=='yamlfmt':
            frame=ttk.Frame(self.tabs);self.tabs.add(frame,text='設定ファイル')
            row=ttk.Frame(frame);row.pack(fill='x')
            for label,callback in [('設定を読み込む',self.load_format_config),('グローバル設定を読み込む',self.load_global_config),('設定を保存',self.save_format_config)]:ttk.Button(row,text=label,command=callback).pack(side='left',padx=3)
            ttk.Label(frame,text='YAML / JSONの設定。空欄の項目はこの設定を引き継ぎます。自動検索は行いません。').pack(anchor='w')
            self.config_text=tk.Text(frame,height=7,wrap='none');self.config_text.pack(fill='both',expand=True);self.config_text.insert('1.0','{}')
        if self.engine=='actionlint':
            config=self.repeat_widgets['@config'];config.configure(height=7,width=80)
            row=ttk.Frame(config.master);row.pack(side='left')
            for label,callback in [('設定を読み込む',self.load_check_config),('設定を保存',self.save_check_config)]:ttk.Button(row,text=label,command=callback).pack(pady=3)
            ttk.Label(self.root,text='GitHub Actionsワークフロー専用の検査です。ワークフローを実行しません。').pack(anchor='w',padx=5)
        if self.engine=='yq':
            widgets=list(self.path_list.master.winfo_children())
            while widgets:
                w=widgets.pop();widgets.extend(w.winfo_children())
                if isinstance(w,ttk.Button) and w.cget('text')=='フォルダーを追加':w.configure(state='disabled')
            ttk.Label(self.root,text='JSON変換でコメント・タグなどが失われる場合があります。複数文書は複数のJSON値になります。').pack(anchor='w',padx=5)

    def _attach_advanced(self):
        prefix='profiles/'+self.engine+'/'
        spec=json.loads(Path(runtime.resource_path(prefix+'advanced-spec.json',self.source_dir)).read_text(encoding='utf8'))
        c=advanced.AdvancedController(self.root,self.profile['tool'],prefix+'upstream-help.txt',spec,self.source_dir)
        c.exe_path=self.native_paths[self.engine];original=c._run
        c._run=lambda:original() if not self._busy() else self.status_var.set('実行中の処理が終わるまでお待ちください。')
        return c

    def _busy(self):
        c=getattr(self,'advanced',None)
        return self._closing or not self.q.empty() or bool(self.worker and self.worker.is_alive()) or str(self.run_btn.cget('state'))=='disabled' or bool(c and (c.running or not c.result_queue.empty() or (c.worker_thread and c.worker_thread.is_alive())))

    def values_snapshot(self):
        values={k:v.get() for k,v in self.values.items()};values.update({k:w.get('1.0','end-1c') for k,w in self.repeat_widgets.items()});return values

    def read_config(self,path):format_view.App.read_config(self,path)
    def load_format_config(self):
        if not self._busy():format_view.App.load_config(self)
    def load_global_config(self):
        if not self._busy():format_view.App.load_global(self)
    def save_format_config(self):
        if self._busy():return
        try:
            _,text=format_view.parse_settings(self.config_text.get('1.0','end-1c'),self.values_snapshot(),self.profile)
            path=filedialog.asksaveasfilename(initialfile='.yamlfmt',defaultextension='.yaml',confirmoverwrite=True)
            if path:Path(path).write_text(text+'\n',encoding='utf8')
        except Exception as e:messagebox.showerror('設定',str(e))
    def load_check_config(self):
        if self._busy():return
        path=filedialog.askopenfilename(filetypes=[('YAML','*.yaml *.yml'),('すべて','*.*')])
        if not path:return
        try:
            with open(path,'rb') as f:data=f.read(128*1024+1)
            if len(data)>128*1024:raise ValueError('設定は128 KiBまでです。')
            text=data.decode('utf-8-sig');w=self.repeat_widgets['@config'];w.delete('1.0','end');w.insert('1.0',text)
        except (OSError,ValueError,UnicodeError) as e:messagebox.showerror('設定',str(e))
    def save_check_config(self):
        if self._busy():return
        path=filedialog.asksaveasfilename(defaultextension='.yaml',confirmoverwrite=True)
        if path:
            try:Path(path).write_text(self.repeat_widgets['@config'].get('1.0','end-1c'),encoding='utf8',newline='')
            except OSError as e:messagebox.showerror('設定',str(e))

    def _poll_queue(self):
        super()._poll_queue()
        r=self.last_result or {}
        if r.get('engine')=='actionlint' and r.get('returncode')==1:self.status_var.set('検査完了: 指摘があります。レポートを保存できます。')
        if r.get('status')=='differences':self.status_var.set('整形が必要な箇所があります。レポートを保存できます。')

    def _on_close(self):
        self._closing=True
        super()._on_close()

    def run(self):
        if self._busy():
            return
        mode_label = self.mode_var.get()
        try:
            mode_id = next(m['id'] for m in self.profile['modes'] if m['label'] == mode_label)
        except StopIteration:
            mode_id = ''
        values = {}
        for f in self.profile['fields']:
            flag = f['flag']
            var = self.values.get(flag)
            if var is None:
                continue
            val = bool(var.get()) if isinstance(var, tk.BooleanVar) else str(var.get())
            values[flag] = val
        for key, txt in self.repeat_widgets.items():
            values[key] = txt.get('1.0', 'end-1c')
        paths = list(self.paths)
        text = self.in_text.get('1.0','end-1c')
        config = self.config_text.get('1.0', 'end-1c') if (hasattr(self, 'config_text') and self.engine == 'yamlfmt') else '{}'
        engine, exe, profile = self.engine, self.exe_path, self.profile
        self.cancel_event.clear()
        self.last_result = None
        self.run_btn.config(state='disabled')
        self.stop_btn.config(state='normal')
        self.status_var.set('実行中…')
        self.worker = threading.Thread(target=self._job, args=(engine, exe, mode_id, values, paths, text, config, profile), daemon=True)
        self.worker.start()

    def _job(self, engine, exe, mode, values, paths, text, config, profile):
        try:
            res = job.execute(engine, exe, mode, values, paths, text, config, profile, self.cancel_event)
            rc = res.get("returncode", -1)
            success = (rc == 0) or (engine == "yamlfmt" and res.get("status") == "differences") or \
                      (engine == "actionlint" and rc == 1)
            self.q.put(("done", rc, res.get("stdout", b""), res.get("stderr", b""), success, res))
        except InterruptedError:self.q.put(('error','処理を停止しました。'))
        except TimeoutError:self.q.put(('error','時間制限に達したため停止しました。'))
        except Exception as e:
            msg = str(e)
            if "cancel" in msg.lower():
                msg = "キャンセルされました。"
            elif "timeout" in msg.lower():
                msg = "タイムアウトしました。"
            self.q.put(("error", msg))

    def result_to_input(self):
        if self._busy() or not self.last_result:
            return
        res = self.last_result
        if not isinstance(res, dict) or res.get("returncode") != 0 or not res.get("transferable"):
            messagebox.showinfo("情報", "この結果は入力として転送できません。")
            return
        out = res.get("stdout", b"")
        if len(out) > 2 * 1024 * 1024:
            messagebox.showerror("エラー", "出力サイズが制限を超えています。")
            return
        try:
            text = out.decode("utf-8")
        except UnicodeDecodeError:
            messagebox.showerror("エラー", "無効なUTF-8文字列です。")
            return
        if "\x00" in text:
            messagebox.showerror("エラー", "NUL文字が含まれています。")
            return

        self._clear_paths()
        self.in_text.delete("1.0", "end")
        self.in_text.insert("1.0", text)

    def switch_engine(self, target):
        if target == self.engine:
            return
        if target not in self.profiles:
            raise ValueError('未対応の用途です。')
        if self._busy():
            self.engine_combo.set(LABELS[self.engine])
            messagebox.showwarning('用途', '処理が終わるか停止してから切り替えてください。')
            return
        shared = (self.in_text.get('1.0', 'end-1c'), self.out_text.get('1.0', 'end-1c'), list(self.paths), self.last_result)
        state = {'mode': self.mode_var.get(), 'values': {k: v.get() for k, v in self.values.items()}, 'repeat': {k: w.get('1.0', 'end-1c') for k, w in self.repeat_widgets.items()}}
        if self.engine == 'yamlfmt' and hasattr(self, 'config_text'):
            state['config'] = self.config_text.get('1.0', 'end-1c')
        self.states[self.engine] = state
        self.root.after_cancel(self._poll_id)
        if self.advanced.toplevel:
            self.advanced._on_toplevel_close()
        self.root.config(menu='')
        for child in self.root.winfo_children():
            child.destroy()
        for attr in ('menubar', 'advanced_menu'):
            if hasattr(self.root, attr):
                delattr(self.root, attr)
        self.engine = target
        self.profile = self.profiles[target]
        self.exe_path = self.native_paths[target]
        state = self.states.get(target, {})
        self.mode_var = tk.StringVar(master=self.root, value=state.get('mode', self.profile['modes'][0]['label']))
        self.values = {}
        for field in self.profile['fields']:
            value = state.get('values', {}).get(field['flag'], field.get('default', False if field['type']=='bool' else ''))
            cls = tk.BooleanVar if field['type'] == 'bool' else tk.StringVar
            self.values[field['flag']] = cls(master=self.root, value=value)
        self.repeat_widgets = {}
        self._build_ui()
        self.in_text.insert('1.0', shared[0])
        self.out_text.configure(state='normal')
        self.out_text.insert('1.0', shared[1])
        self.out_text.configure(state='disabled')
        self.paths = shared[2]
        self.last_result = shared[3]
        for path in self.paths:
            self.path_list.insert('end', path)
        for name, text in state.get('repeat', {}).items():
            w = self.repeat_widgets[name]
            w.delete('1.0', 'end')
            w.insert('1.0', text)
        if target == 'yamlfmt' and hasattr(self, 'config_text'):
            cfg = state.get('config', '{}')
            self.config_text.delete('1.0', 'end')
            self.config_text.insert('1.0', cfg)

if __name__=='__main__':App(Path(__file__).resolve().parent).root.mainloop()
