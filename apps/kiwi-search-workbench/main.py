"""Find files and search their contents with a shared target and filters."""
import csv,json,os,queue,sys,threading,tkinter as tk
from pathlib import Path
from tkinter import ttk,filedialog,messagebox
sys.path.insert(0,str(Path(__file__).resolve().parent.parent/'common'))
import runtime,advanced
from worker import execute_job, _is_link_or_ancestor_link

COMMON={'folder':'','extensions':'','excludes':'','hidden':False,'ignored':False,'depth':''}
NAME={'pattern':'','pattern_mode':'literal','case':'auto','full_path':False}
CONTENT={'pattern':'','pattern_mode':'literal','case':'auto','word':False,'whole_line':False,'multiline':False,'context':'0','max_count':'','encoding':'auto'}

def visible(text):
    return ''.join('\\n' if c=='\n' else '\\r' if c=='\r' else '\\t' if c=='\t' else f'\\u{ord(c):04x}' if ord(c)<32 or 127<=ord(c)<160 else c for c in str(text))

class SearchAdvancedController(advanced.AdvancedController):
    def _run(self):
        if self.app._busy():
            messagebox.showwarning('実行中', '別の検索が進行中です。', parent=self.toplevel)
            return
        super()._run()

class App(tk.Tk):
    def __init__(self,source_dir,native_paths=None):
        super().__init__();self.source_dir=Path(source_dir);self.title('きうい検索作業場');self.geometry('1140x850');self.minsize(860,620)
        self.native_paths={e:str((native_paths or {}).get(e,runtime.resource_path(e+'.exe',self.source_dir))) for e in ('fd','rg')}
        self.common=self._variables(COMMON);self.name_options=self._variables(NAME);self.content_options=self._variables(CONTENT)
        self.status=tk.StringVar(master=self,value='フォルダーを指定して、名前や内容を検索してください。');self.scope_status=tk.StringVar(master=self,value='内容検索の対象: フォルダー全体')
        self.q=queue.Queue();self.worker=None;self.running=False;self.cancel_event=threading.Event();self.results={};self.file_signature=None;self.scope_paths=[];self.scope_signature=None
        self._build_ui();self.details={}
        self.protocol('WM_DELETE_WINDOW',self._close)
        for engine in ('fd','rg'):
            prefix=f'profiles/{engine}/';spec=json.loads(Path(runtime.resource_path(prefix+'advanced-spec.json',self.source_dir)).read_text(encoding='utf8'))
            ctrl=SearchAdvancedController(self,engine+'.exe',prefix+'upstream-help.txt',spec,self.source_dir);ctrl.exe_path=self.native_paths[engine];self.details[engine]=ctrl
        self.advanced_menu.delete(0,'end')
        for engine,label in [('fd','ファイル名検索の詳細'),('rg','内容検索の詳細')]:self.advanced_menu.add_command(label=label,command=lambda e=engine:self._open_detail(e))
        for var in self.common.values():var.trace_add('write',lambda *_:self._invalidate_scope())
        self._poll_id=self.after(100,self._poll)

    def _variables(self,defaults):
        return {k:(tk.BooleanVar(master=self,value=v) if isinstance(v,bool) else tk.StringVar(master=self,value=v)) for k,v in defaults.items()}

    def _build_ui(self):
        common=ttk.LabelFrame(self,text='共通の対象と除外',padding=8);common.pack(fill='x',padx=8,pady=5)
        ttk.Label(common,text='フォルダー').grid(row=0,column=0,sticky='w');ttk.Entry(common,textvariable=self.common['folder']).grid(row=0,column=1,columnspan=3,sticky='ew',padx=5)
        ttk.Button(common,text='選択…',command=self._choose_folder).grid(row=0,column=4)
        ttk.Label(common,text='拡張子（カンマ区切り）').grid(row=1,column=0,sticky='w');ttk.Entry(common,textvariable=self.common['extensions'],width=22).grid(row=1,column=1,sticky='ew',padx=5)
        ttk.Label(common,text='最大の深さ（空欄は無制限）').grid(row=1,column=2,sticky='e');ttk.Entry(common,textvariable=self.common['depth'],width=8).grid(row=1,column=3,sticky='w',padx=5)
        ttk.Checkbutton(common,text='隠しファイルを含める',variable=self.common['hidden']).grid(row=2,column=1,sticky='w')
        ttk.Checkbutton(common,text='ignore設定を無視',variable=self.common['ignored']).grid(row=2,column=2,columnspan=2,sticky='w')
        ttk.Label(common,text='除外glob（1行1個）').grid(row=3,column=0,sticky='w');self.exclude_text=tk.Text(common,height=2,wrap='none');self.exclude_text.grid(row=3,column=1,columnspan=4,sticky='ew',padx=5)
        self.exclude_text.bind('<<Modified>>',self._sync_excludes);common.columnconfigure(1,weight=1);common.columnconfigure(3,weight=1)
        self.tabs=ttk.Notebook(self);self.tabs.pack(fill='both',expand=True,padx=8,pady=5)
        self.name_tab=ttk.Frame(self.tabs,padding=8);self.content_tab=ttk.Frame(self.tabs,padding=8)
        self.tabs.add(self.name_tab,text='ファイル名');self.tabs.add(self.content_tab,text='内容')
        self._fields(self.name_tab,self.name_options,[('pattern','名前に含む文字',None),('pattern_mode','検索方法',['literal','regex','glob']),('case','大小文字',['auto','sensitive','ignore']),('full_path','フォルダー名も検索',None)])
        row=ttk.Frame(self.name_tab);row.pack(fill='x',pady=4)
        self.name_run=ttk.Button(row,text='ファイル名を検索',command=lambda:self._start('fd'));self.name_run.pack(side='left',padx=2)
        ttk.Button(row,text='選んだファイルの内容を検索',command=lambda:self._transfer(True)).pack(side='left',padx=2)
        ttk.Button(row,text='表示中のファイルの内容を検索',command=lambda:self._transfer(False)).pack(side='left',padx=2)
        self.name_tree=self._result_tree(self.name_tab,[('name','ファイル名',250),('folder','場所',700)])
        self._fields(self.content_tab,self.content_options,[('pattern','探す文字列・式',None),('pattern_mode','検索方法',['literal','regex','pcre2']),('case','大小文字',['auto','sensitive','ignore']),('word','単語全体',None),('whole_line','行全体',None),('multiline','複数行',None),('context','前後の行数',None),('max_count','1ファイルの一致上限',None),('encoding','文字コード',['auto','utf-8','utf-16','shift_jis'])])
        row=ttk.Frame(self.content_tab);row.pack(fill='x',pady=4)
        self.content_run=ttk.Button(row,text='内容を検索',command=lambda:self._start('rg'));self.content_run.pack(side='left',padx=2)
        ttk.Button(row,text='フォルダー全体に戻す',command=self._folder_scope).pack(side='left',padx=2)
        ttk.Label(self.content_tab,textvariable=self.scope_status).pack(anchor='w')
        ttk.Label(self.content_tab,text='選択ファイルでは元の名前検索の対象を使い、ignore・globの走査条件を再適用しません。').pack(anchor='w')
        self.content_tree=self._result_tree(self.content_tab,[('kind','種類',65),('file','ファイル',370),('line','行',55),('text','内容',550)])
        self.content_tree.tag_configure('context',foreground='#666666')
        controls=ttk.Frame(self);controls.pack(fill='x',padx=8,pady=6)
        self.stop_button=ttk.Button(controls,text='停止',command=self.cancel_event.set,state='disabled');self.stop_button.pack(side='left',padx=2)
        ttk.Button(controls,text='選択ファイルを開く',command=self._open_file).pack(side='left',padx=2)
        ttk.Button(controls,text='結果を保存',command=lambda:self._save_result(False)).pack(side='left',padx=2)
        ttk.Button(controls,text='CLI原文を保存',command=lambda:self._save_result(True)).pack(side='left',padx=2)
        ttk.Label(self,textvariable=self.status,padding=(8,2)).pack(fill='x')
        ttk.Label(self,text='literal:文字どおり / regex:正規表現 / glob:ワイルドカード / auto:大文字を含む式だけ大小文字を区別',padding=(8,2)).pack(fill='x')

    def _fields(self,parent,variables,fields):
        area=ttk.Frame(parent);area.pack(fill='x')
        for i,(name,label,choices) in enumerate(fields):
            if i==0:
                ttk.Label(area,text=label).grid(row=0,column=0,sticky='w');ttk.Entry(area,textvariable=variables[name]).grid(row=0,column=1,columnspan=5,sticky='ew',padx=5)
            else:
                row=(i-1)//3+1;col=((i-1)%3)*2
                if isinstance(variables[name],tk.BooleanVar):ttk.Checkbutton(area,text=label,variable=variables[name]).grid(row=row,column=col,columnspan=2,sticky='w')
                else:
                    ttk.Label(area,text=label).grid(row=row,column=col,sticky='w')
                    widget=ttk.Combobox(area,textvariable=variables[name],values=choices,state='readonly',width=13) if choices else ttk.Entry(area,textvariable=variables[name],width=10)
                    widget.grid(row=row,column=col+1,sticky='ew',padx=5)
        for col in (1,3,5):area.columnconfigure(col,weight=1)

    def _result_tree(self,parent,columns):
        frame=ttk.Frame(parent);frame.pack(fill='both',expand=True,pady=5)
        tree=ttk.Treeview(frame,columns=[c[0] for c in columns],show='headings',selectmode='extended')
        for key,label,width in columns:tree.heading(key,text=label);tree.column(key,width=width,minwidth=45)
        vertical=ttk.Scrollbar(frame,orient='vertical',command=tree.yview);horizontal=ttk.Scrollbar(frame,orient='horizontal',command=tree.xview);tree.configure(yscrollcommand=vertical.set,xscrollcommand=horizontal.set)
        tree.grid(row=0,column=0,sticky='nsew');vertical.grid(row=0,column=1,sticky='ns');horizontal.grid(row=1,column=0,sticky='ew');frame.rowconfigure(0,weight=1);frame.columnconfigure(0,weight=1)
        return tree

    def _sync_excludes(self,event=None):
        if self.exclude_text.edit_modified():
            self.common['excludes'].set(self.exclude_text.get('1.0','end-1c'));self.exclude_text.edit_modified(False)

    def _choose_folder(self):
        folder=filedialog.askdirectory()
        if folder:self.common['folder'].set(folder)

    def _start(self, engine: str) -> None:
        if self._busy():
            messagebox.showwarning('実行中', '別の検索が進行中です。')
            return
        self._sync_excludes()
        folder = self.common['folder'].get().strip()
        if not folder or not Path(folder).is_dir():
            self.status.set('共通フォルダーを指定してください。')
            return

        sig = self._signature()
        options = {k: v.get() for k, v in self.common.items()}
        options.update({k: v.get() for k, v in (self.name_options if engine == 'fd' else self.content_options).items()})

        paths = []
        if engine == 'rg':
            if self.scope_paths and self.scope_signature != sig:
                self.status.set('検索対象が古くなっています。再検索するかフォルダー全体に戻してください。')
                return
            if self.scope_paths:
                paths = list(self.scope_paths)

        exe = self.native_paths[engine]
        self.results.pop(engine, None)
        tree = self.name_tree if engine == 'fd' else self.content_tree
        for iid in tree.get_children():
            tree.delete(iid)

        if engine == 'fd':
            self.file_signature = None
            self._folder_scope()
        self.running = True
        self.cancel_event.clear()
        self.status.set('検索を開始しました…')
        self.name_run.config(state='disabled')
        self.content_run.config(state='disabled')
        self.stop_button.config(state='normal')

        self.worker = threading.Thread(target=self._job, args=(engine, exe, options, paths, sig), daemon=True)
        self.worker.start()

    def _job(self, engine: str, exe: str, options: dict, paths: list, signature: tuple) -> None:
        try:
            result = execute_job(exe, engine, options, paths, self.cancel_event)
            result['options'] = options
            self.q.put(('done', engine, result, signature))
        except InterruptedError:
            self.q.put(('error', engine, '停止しました。'))
        except Exception as e:
            self.q.put(('error', engine, str(e)))

    def _poll(self) -> None:
        try:
            while True:
                item = self.q.get_nowait()
                kind = item[0]
                if kind == 'done':
                    _, engine, result, sig = item
                    rc = result.get('returncode', -1)
                    stderr_text = result.get('stderr', b'').decode('utf8', errors='replace').strip()[:2000]
                    ok = (rc == 0) if engine == 'fd' else (rc in (0, 1))

                    self.results[engine] = result
                    tree = self.name_tree if engine == 'fd' else self.content_tree
                    for iid in tree.get_children():
                        tree.delete(iid)

                    rows = result.get('rows', [])
                    total_matches = result.get('total', len(rows))
                    total_lines = result.get('total_lines', len(rows))
                    displayed = min(len(rows), 1000)

                    for i, row in enumerate(rows[:displayed]):
                        if engine == 'fd':
                            p = Path(row['path'])
                            tree.insert('', 'end', iid=str(i), values=(visible(p.name), visible(str(p.parent))))
                        else:
                            kind_jp = '一致' if row.get('kind') == 'match' else '前後'
                            vals = (kind_jp, visible(row['path']), str(row.get('line', '')), visible(row.get('text', '')))
                            iid = tree.insert('', 'end', iid=str(i), values=vals)
                            if row.get('kind') != 'match':
                                tree.item(iid, tags=('context',))

                    if engine == 'fd':
                        if ok:
                            self.file_signature = sig if sig == self._signature() else None
                        else:
                            self.file_signature = None
                        if ok:
                            self.status.set(f'fd 完了: {total_matches}件 (表示{displayed}件)')
                        else:
                            self.status.set(f'fd 失敗 rc={rc}: {stderr_text}')
                    elif engine == 'rg':
                        if ok:
                            self.status.set(f'rg 完了: 一致{total_matches}件 / 行{total_lines}件 (表示{displayed}件)')
                        else:
                            self.status.set(f'rg 失敗 rc={rc}: {stderr_text}')

                elif kind == 'error':
                    _, engine, msg = item
                    if engine == 'fd':
                        self.file_signature = None
                    self.status.set(f'{engine} エラー: {msg}')

                if not self.q.empty():
                    continue
                break
        except queue.Empty:
            pass
        finally:
            worker_dead = (self.worker is None) or (not self.worker.is_alive())
            if worker_dead and self.q.empty():
                self.running = False
                self.name_run.config(state='normal')
                self.content_run.config(state='normal')
                self.stop_button.config(state='disabled')
            self._poll_id = self.after(100, self._poll)

    def _transfer(self, selected: bool) -> None:
        if self._busy():
            messagebox.showwarning('実行中', '別の検索が進行中です。')
            return
        sig = self._signature()
        if self.file_signature != sig or not self.results.get('fd'):
            self.status.set('ファイル名検索の結果が古くなっています。再検索してください。')
            return
        fd_result = self.results['fd']
        if fd_result.get('returncode', -1) != 0:
            self.status.set('ファイル名検索に失敗しています。')
            return
        rows = fd_result.get('rows', [])
        tree = self.name_tree
        iids = tree.selection() if selected else [str(i) for i in range(len(rows))]
        paths = []
        for iid in iids:
            try:
                idx = int(iid)
                if 0 <= idx < len(rows):
                    p = rows[idx]['path']
                    if p not in paths:
                        paths.append(p)
            except (ValueError, IndexError, KeyError):
                continue
        if not paths:
            self.status.set('対象ファイルがありません。')
            return
        if len(paths) > 200:
            self.status.set(f'選択が{len(paths)}件です。200件以下にしてください。')
            return
        self.scope_paths = list(paths)
        self.scope_signature = sig
        self.scope_status.set(f'内容検索の対象: {len(paths)}ファイル')
        self.tabs.select(self.content_tab)
        self._start('rg')

    def _busy(self):
        return self.running or bool(self.worker and self.worker.is_alive()) or any(c.running or bool(c.worker_thread and c.worker_thread.is_alive()) for c in self.details.values())

    def _signature(self):
        return tuple((key, var.get()) for key, var in sorted(self.common.items()))

    def _invalidate_scope(self):
        self.file_signature = None
        self._folder_scope()
        self.status.set('対象や除外条件が変わりました。ファイル名検索の結果は再検索してください。')

    def _folder_scope(self):
        self.scope_paths = []
        self.scope_signature = None
        self.scope_status.set('内容検索の対象: フォルダー全体')

    def _open_detail(self, engine):
        if self._busy():
            messagebox.showwarning('実行中', '検索を停止するか、完了してから詳細機能を開いてください。')
            return
        self.details[engine].open_window()

    def _active_engine(self):
        return 'fd' if self.tabs.select() == str(self.name_tab) else 'rg'

    def _open_file(self):
        if self._busy():
            return
        engine = self._active_engine()
        tree = self.name_tree if engine == 'fd' else self.content_tree
        result = self.results.get(engine)
        if not result or not tree.selection():
            return
        try:
            row = result['rows'][int(tree.selection()[0])]
            path = Path(row['path'])
            root = Path(result['options']['folder']).resolve()
            if not path.is_file() or _is_link_or_ancestor_link(str(path)) or not path.resolve().is_relative_to(root):
                raise ValueError('対象内の通常のファイルだけを開けます。')
            os.startfile(str(path))
        except (OSError, ValueError, IndexError, KeyError) as error:
            messagebox.showerror('ファイルを開けません', str(error))

    def _save_result(self, raw):
        result = self.results.get(self._active_engine())
        if not result:
            return
        suffix = '.bin' if raw else '.json' if self._active_engine() == 'fd' else '.csv'
        filename = filedialog.asksaveasfilename(parent=self, defaultextension=suffix, confirmoverwrite=False)
        if not filename:
            return
        path = Path(filename)
        if path.exists() and not messagebox.askyesno('保存', 'ファイルが存在します。上書きしますか？', parent=self):
            return
        try:
            if raw:
                path.write_bytes(result['stdout'])
            elif self._active_engine() == 'fd':
                path.write_text(json.dumps([row['path'] for row in result['rows']], ensure_ascii=False, indent=2), encoding='utf8')
            else:
                with path.open('w', encoding='utf-8-sig', newline='') as handle:
                    writer = csv.writer(handle)
                    writer.writerow(['file', 'line', 'kind', 'text'])
                    for row in result['rows']:
                        writer.writerow([row['path'], row['line'], row['kind'], row['text']])
            self.status.set('検索結果を保存しました。')
        except OSError as error:
            messagebox.showerror('保存できません', str(error))

    def _close(self):
        self.cancel_event.set()
        for controller in self.details.values():
            controller.cancel_event.set()
        if bool(self.worker and self.worker.is_alive()) or any(c.worker_thread and c.worker_thread.is_alive() for c in self.details.values()):
            self.after(50, self._close)
            return
        for callback in self.tk.splitlist(self.tk.call('after', 'info')):
            self.after_cancel(callback)
        self.destroy()

if __name__ == '__main__':
    App(Path(__file__).resolve().parent).mainloop()
