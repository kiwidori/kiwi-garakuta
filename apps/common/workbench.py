import os, sys, re, threading, queue, tkinter as tk
from tkinter import ttk, filedialog, messagebox
from pathlib import Path
try:
    from apps.common import runtime, advanced
except ImportError:
    import runtime, advanced

MAX_IN=2*1024*1024; MAX_OUT=16*1024*1024

def build_args(profile, values, mode, paths):
    args=[]
    m = next((x for x in profile.get('modes',[]) if x['label']==mode), None)
    if not m: raise ValueError('操作を選択してください。')
    args.extend(m.get('args',[]))
    if not m.get('files') and not m.get('stdin'): return args
    for f in profile.get('fields',[]):
        v=values.get(f['flag'], f.get('default',''))
        if f['type'] == 'bool':
            if v: args.append(f['flag'])
        elif f['type'] == 'text':
            if not v: continue
            if f.get('repeat'):
                for line in str(v).splitlines():
                    line=line.strip()
                    if line: args.extend([f['flag'], line])
            else:
                args.extend([f['flag'], str(v)])
        elif f['type']=='choice':
            if not v: continue
            args.extend([f['flag'], v])
    if m.get('files'):
        if paths and profile.get('delimiter'): args.append('--')
        for p in paths:
            args.append(str(Path(p).absolute()))
    return args

class App:
    def __init__(self, profile, source_dir):
        self.profile=profile; self.source_dir=source_dir
        self.root=tk.Tk(); self.root.title(profile['title'])
        self.root.geometry("1100x850")
        self.mode_var=tk.StringVar(value=profile['modes'][0]['label'] if profile.get('modes') else '')
        self.values={}
        for f in profile.get('fields',[]):
            if f['type'] == 'bool':
                self.values[f['flag']] = tk.BooleanVar(value=bool(f.get('default')))
            else:
                self.values[f['flag']] = tk.StringVar(value=str(f.get('default','')))
        self.paths=[]; self.path_list=None; self.repeat_widgets={}
        self.in_text=None; self.out_text=None
        self.status_var=tk.StringVar(value="待機中")
        self.exe_path=runtime.resource_path(profile['tool'],source_dir)
        self.last_result=None; self.cancel_event=threading.Event(); self.q=queue.Queue()
        self.worker=None; self._build_ui()

    def _build_ui(self):
        p=self.profile
        mode_row=ttk.Frame(self.root); mode_row.pack(fill='x', padx=5, pady=2)
        ttk.Label(mode_row, text="操作:").pack(side='left')
        self.mode_combo=ttk.Combobox(mode_row, values=[m['label'] for m in p.get('modes',[])], textvariable=self.mode_var, state='readonly', width=30)
        self.mode_combo.set(self.mode_var.get()); self.mode_combo.pack(side='left', padx=5)
        self.mode_combo.bind('<<ComboboxSelected>>', lambda e: self.mode_var.set(self.mode_combo.get()))

        tabs=self.tabs=ttk.Notebook(self.root); tabs.pack(fill='both', expand=True, padx=5, pady=2)
        groups={}
        for f in p.get('fields',[]):
            g=f.get('group','General')
            if g not in groups:
                frame=ttk.Frame(tabs); tabs.add(frame, text=g)
                # Settings tab max height 300 with scroll
                canvas=tk.Canvas(frame, highlightthickness=0, height=250)
                sb=ttk.Scrollbar(frame, orient='vertical', command=canvas.yview)
                inner=tk.Frame(canvas); inner.bind('<Configure>', lambda e,c=canvas: c.configure(scrollregion=c.bbox("all")))
                canvas.create_window((0,0), window=inner, anchor='nw'); canvas.configure(yscrollcommand=sb.set)
                canvas.pack(side='left', fill='both', expand=True); sb.pack(side='right', fill='y')
                groups[g]=(frame, inner)
            _, inner = groups[g]
            if f['type']=='bool':
                ttk.Checkbutton(inner, text=f['label'], variable=self.values[f['flag']]).pack(anchor='w')
            elif f['type']=='choice':
                row=ttk.Frame(inner); row.pack(fill='x', pady=1)
                ttk.Label(row, text=f['label']).pack(side='left')
                ttk.Combobox(row, values=['']+f.get('choices',[]), state='readonly', width=20, textvariable=self.values[f['flag']]).pack(side='left', padx=5)
            else:
                row=ttk.Frame(inner); row.pack(fill='x', pady=1)
                ttk.Label(row, text=f['label']).pack(side='left')
                if f.get('repeat'):
                    widget=tk.Text(row,width=45,height=2,wrap='none')
                    widget.insert('1.0',self.values[f['flag']].get())
                    widget.pack(side='left',padx=5)
                    self.repeat_widgets[f['flag']]=widget
                else:
                    ttk.Entry(row, width=45, textvariable=self.values[f['flag']]).pack(side='left', padx=5)

        in_frame=ttk.LabelFrame(self.root, text="標準入力（パスを使う場合は空欄）"); in_frame.pack(fill='both', expand=True, padx=5, pady=2)
        self.in_text=tk.Text(in_frame, width=60, height=5)
        self.in_text.pack(side='left', fill='both', expand=True)
        in_sb=ttk.Scrollbar(in_frame, orient='vertical', command=self.in_text.yview); in_sb.pack(side='right', fill='y')
        self.in_text.configure(yscrollcommand=in_sb.set)

        path_frame=ttk.LabelFrame(self.root, text="対象ファイル・フォルダー"); path_frame.pack(fill='x', padx=5, pady=2)
        btns=ttk.Frame(path_frame); btns.pack(fill='x')
        ttk.Button(btns, text="ファイルを追加", command=self._add_file).pack(side='left', padx=2)
        ttk.Button(btns, text="フォルダーを追加", command=self._add_folder).pack(side='left', padx=2)
        ttk.Button(btns, text="選択を削除", command=self._remove_path).pack(side='left', padx=2)
        ttk.Button(btns, text="一覧をクリア", command=self._clear_paths).pack(side='left', padx=2)
        self.path_list=tk.Listbox(path_frame,height=3)
        self.path_list.pack(fill='x', pady=(5,0))

        out_frame=ttk.LabelFrame(self.root, text="結果"); out_frame.pack(fill='both', expand=True, padx=5, pady=2)
        self.out_text=tk.Text(out_frame, width=60, height=10, state='disabled')
        self.out_text.pack(side='left', fill='both', expand=True)
        out_sb=ttk.Scrollbar(out_frame, orient='vertical', command=self.out_text.yview); out_sb.pack(side='right', fill='y')
        self.out_text.configure(yscrollcommand=out_sb.set)

        ctrl=ttk.Frame(self.root); ctrl.pack(fill='x', padx=5, pady=5)
        self.run_btn=ttk.Button(ctrl, text="実行", command=self.run); self.run_btn.pack(side='left', padx=2)
        self.stop_btn=ttk.Button(ctrl, text="停止", command=self._stop, state='disabled'); self.stop_btn.pack(side='left', padx=2)
        ttk.Button(ctrl, text="結果を保存", command=self._save).pack(side='left', padx=2)
        ttk.Label(ctrl, textvariable=self.status_var).pack(side='right')

        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self.advanced = advanced.attach(self.root, self.source_dir)
        self._poll_id=self.root.after(100, self._poll_queue)

    def _add_file(self):
        f=filedialog.askopenfilename()
        if f: self.paths.append(f); self.path_list.insert('end', f)

    def _add_folder(self):
        d=filedialog.askdirectory()
        if d: self.paths.append(d); self.path_list.insert('end', d)

    def _remove_path(self):
        sel=self.path_list.curselection()
        if not sel: return
        idx=sel[0]
        del self.paths[idx]
        self.path_list.delete(idx)

    def _clear_paths(self):
        sel=self.path_list.curselection()
        self.path_list.delete(0,'end')
        self.paths=[]

    def run(self):
        if self.worker and self.worker.is_alive(): return
        mode=self.mode_var.get()
        m=next((x for x in self.profile['modes'] if x['label']==mode), None)
        if not m: return

        text_str=self.in_text.get('1.0','end-1c')
        information=not m.get('stdin') and not m.get('files')
        if not information and self.paths and not m.get('files'):
            messagebox.showerror('入力','この操作では標準入力を使います。一覧をクリアしてください。');return
        if not information and self.paths and text_str.strip():
            messagebox.showerror('入力','パスと標準入力は同時に指定できません。標準入力を空にしてください。');return
        # Determine input source based on mode and paths
        has_paths = len(self.paths) > 0
        use_stdin = False
        stdin_data = b''

        if m.get('stdin'):
            if not has_paths:
                text_str = self.in_text.get('1.0','end-1c')
                if not text_str.strip():
                    messagebox.showerror("Error", "標準入力が空です。"); return
                stdin_data = text_str.encode('utf-8')
                use_stdin = True
            else:
                # Files are used only after rejecting simultaneous text input above.
                pass
        elif m.get('files'):
            if not has_paths:
                messagebox.showerror("Error", "対象ファイルが指定されていません。"); return

        if use_stdin and len(stdin_data) > MAX_IN:
            messagebox.showerror("Error", "入力サイズが2MiBを超えています。"); return

        paths=[]
        for p in ([] if information else self.paths):
            ap=os.path.abspath(p)
            if '\x00' in ap:
                messagebox.showerror("Error", "無効なパスです。"); return
            if not os.path.exists(ap):
                messagebox.showerror("Error", "パスが存在しません。"); return
            paths.append(ap)
        values={k:(v.get() if isinstance(v, tk.BooleanVar) else v.get()) for k,v in self.values.items()}
        values.update({k:w.get('1.0','end-1c') for k,w in self.repeat_widgets.items()})
        if self.profile['slug']=='kiwi-minify' and use_stdin and not values.get('--type'):
            messagebox.showerror('入力','標準入力を圧縮するときは入力形式を選択してください。');return

        # Validate mode-specific constraints
        if not m.get('allow_dirs', True):
            for p in paths:
                if os.path.isdir(p):
                    messagebox.showerror("Error", "この操作ではフォルダーを指定できません。"); return

        args=build_args(self.profile, values, mode, paths)
        blocked=self.profile.get('blocked_flags',[])

        self.cancel_event.clear()
        self.last_result=None
        self.run_btn.config(state='disabled'); self.stop_btn.config(state='normal')
        self.status_var.set("実行中...")
        # Clear output at start
        self.out_text.config(state='normal'); self.out_text.delete('1.0','end'); self.out_text.config(state='disabled')
        self.worker=threading.Thread(target=self._worker, args=(args, stdin_data, m), daemon=True)
        self.worker.start()

    def _worker(self, args, stdin_data, mode_def):
        try:
            exe = self.exe_path if hasattr(self, 'exe_path') and self.exe_path else runtime.resource_path(self.profile['tool'], self.source_dir)
            from workbench_jobs import execute_job
            result=execute_job(self.profile,exe,args,stdin_data,self.cancel_event,mode_def)
            out=result['stdout']; err=result['stderr']
            rc=result['returncode']
            success = rc in mode_def.get('success_codes',[0])
            self.q.put(('done', rc, out, err, success, result))
        except InterruptedError:
            self.q.put(('error', "処理を停止しました。"))
        except TimeoutError:
            self.q.put(('error', "時間制限に達したため停止しました。"))
        except Exception as e:
            self.q.put(('error', str(e)))

    def _stop(self):
        self.cancel_event.set()
        self.status_var.set("停止中...")

    def _poll_queue(self):
        try:
            while True:
                item=self.q.get_nowait()
                if item[0]=='done':
                    rc, out, err, success = item[1], item[2], item[3], item[4]
                    if success:
                        self.last_result=item[5]
                    else:
                        self.last_result=None
                    # Display stdout and stderr
                    display_out = item[5].get('display',runtime._strip_ansi(out.decode('utf-8','replace'))[:MAX_OUT])
                    display_err = err.decode('utf-8','replace')[:MAX_OUT//4]
                    full_display = display_out
                    if display_err:
                        full_display += "\n--- 標準エラー ---\n" + display_err
                    self.out_text.config(state='normal'); self.out_text.delete('1.0','end')
                    self.out_text.insert('1.0', full_display); self.out_text.config(state='disabled')
                    if success:
                        self.status_var.set(f"完了 (rc={rc})")
                    else:
                        self.status_var.set(f"失敗 (rc={rc})")
                elif item[0]=='error':
                    self.last_result={'error':item[1]}
                    self.out_text.config(state='normal'); self.out_text.delete('1.0','end')
                    self.out_text.insert('1.0', item[1]); self.out_text.config(state='disabled')
                    self.status_var.set(f"エラー: {item[1]}")
                self.run_btn.config(state='normal'); self.stop_btn.config(state='disabled')
        except queue.Empty:
            pass
        if not (self.worker and self.worker.is_alive()):
            self.run_btn.config(state='normal'); self.stop_btn.config(state='disabled')
        self._poll_id=self.root.after(100, self._poll_queue)

    def _save(self):
        if not self.last_result or 'stdout' not in self.last_result: return
        f=filedialog.asksaveasfilename(defaultextension=self.last_result.get('extension','.txt'), filetypes=[("すべてのファイル", "*.*")])
        if not f: return
        if os.path.exists(f) and not messagebox.askyesno("確認", "ファイルが存在します。上書きしますか？"): return
        try:
            with open(f,'wb') as fh: fh.write(self.last_result['stdout'])
        except OSError as error:messagebox.showerror('保存エラー',str(error))

    def _on_close(self):
        self.cancel_event.set()
        if self.worker and self.worker.is_alive():
            self.root.after(50,self._on_close);return
        for timer in self.root.tk.call('after','info'):
            self.root.after_cancel(timer)
        self.root.destroy()

def launch(profile, source_dir):
    app=App(profile, source_dir)
    app.root.mainloop()
    return app
