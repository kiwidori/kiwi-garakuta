"""A small offline PDF workbench for Windows."""
import copy,json,os,queue,sys,threading,tkinter as tk
from pathlib import Path
from tkinter import ttk,filedialog,messagebox
from core import run_job,build_job,validate_extra
from runtime import resource_path
OP_LABELS={'PDFを結合':'merge','ページを取り出す・並べ替える':'extract','ページごとに分割':'split','ページを回転':'rotate','容量を最適化':'optimize','パスワードを設定':'protect','パスワードを解除':'unlock','PDFをチェック':'check','詳細設定':'advanced'}
ANGLES={'右へ90°':'+90','左へ90°':'-90','180°':'+180','回転指定を0°にする':'0'}
class App(tk.Tk):
    def __init__(self):
        super().__init__();self.title('きういPDF');self.geometry('1000x730');self.minsize(930,680)
        self.rows=[];self.current_row=None;self.controls=[];self.option_frames={};self.q=queue.Queue();self.cancel=threading.Event();self.worker=None;self.closing=False;self.last_output='';self.pending_row=None
        self.operation=tk.StringVar(value='PDFを結合');self.page_var=tk.StringVar();self.password_var=tk.StringVar();self.output_var=tk.StringVar();self.angle_var=tk.StringVar(value='右へ90°');self.chunk_var=tk.StringVar(value='1');self.lossy_var=tk.BooleanVar();self.web_var=tk.BooleanVar();self.open_password_var=tk.StringVar();self.owner_password_var=tk.StringVar();self.status_var=tk.StringVar(value='PDFを追加してください。外部へのアップロードは行いません。');self.advanced_json='{}'
        self._build_ui();self.protocol('WM_DELETE_WINDOW',self.close);self.after(100,self.poll)

    def _build_ui(self):
        import tkinter as tk
        from tkinter import ttk
        root = self
        root.geometry("1000x730")
        root.title("きういPDF")

        style = ttk.Style()
        try:
            style.configure("Title.TLabel", font=("Meiryo UI", 18, "bold"))
            style.configure("Sub.TLabel", font=("Meiryo UI", 10))
            style.configure("Muted.TLabel", foreground="#666")
        except Exception:
            pass

        main = ttk.Frame(root, padding=14)
        main.pack(fill="both", expand=True)

        ttk.Label(main, text="PDFをまとめる。必要なページだけ残す。", style="Title.TLabel").pack(anchor="w")
        ttk.Label(main, text="結合・ページの取り出し・分割・回転を、このPCの中だけで行えます。", style="Sub.TLabel").pack(anchor="w", pady=(0, 10))

        toolbar = ttk.Frame(main)
        toolbar.pack(fill="x")
        self.controls = []

        def add_btn(text, cmd):
            b = ttk.Button(toolbar, text=text, command=cmd)
            b.pack(side="left", padx=2)
            self.controls.append(b)

        add_btn("追加", self.add_files)
        add_btn("一覧から外す", self.remove_files)
        add_btn("上へ", self.move_up)
        add_btn("下へ", self.move_down)
        add_btn("元ファイルを開く", self.open_source)

        tree_frame = ttk.Frame(main)
        tree_frame.pack(fill="x", pady=10)
        cols = ("name", "range", "count", "size")
        self.tree = ttk.Treeview(tree_frame, columns=cols, show="headings", selectmode="browse", height=6)
        for c in cols:
            self.tree.heading(c, text={"name": "ファイル名", "range": "ページ範囲", "count": "ページ数", "size": "サイズ"}[c])
            self.tree.column(c, width={"name": 400, "range": 170, "count": 90, "size": 100}[c], stretch=(c=="name"))
        sb = ttk.Scrollbar(tree_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=sb.set)
        self.tree.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        self.tree.bind("<<TreeviewSelect>>", self.selection_changed)

        src_frame = ttk.LabelFrame(main, text="選択したPDF", padding=8)
        src_frame.pack(fill="x", pady=(0, 10))

        row1 = ttk.Frame(src_frame); row1.pack(fill="x")
        ttk.Label(row1, text="このPDFのページ（空欄＝すべて）").pack(side="left")
        e_page = ttk.Entry(row1, textvariable=self.page_var, width=22)
        e_page.pack(side="left", padx=5)
        self.controls.append(e_page)

        ttk.Label(row1, text="入力PDFのパスワード").pack(side="left")
        e_pass = ttk.Entry(row1, textvariable=self.password_var, show="*", width=22)
        e_pass.pack(side="left", padx=5)
        self.controls.append(e_pass)

        b_count = ttk.Button(row1, text="ページ数を確認", command=self.count_pages)
        b_count.pack(side="left", padx=5)
        self.controls.append(b_count)

        b_save = ttk.Button(row1, text="反映", command=self.save_fields)
        b_save.pack(side="left")
        self.controls.append(b_save)

        ttk.Label(src_frame, text="ページの例: 1,3-5 ／ 5-1（逆順）", style="Muted.TLabel").pack(anchor="w")

        op_row = ttk.Frame(main); op_row.pack(fill="x", pady=5)
        self.operation_box = ttk.Combobox(op_row, textvariable=self.operation, values=list(OP_LABELS.keys()), state="readonly", width=31)
        self.operation_box.pack(side="left")
        self.operation_box.bind("<<ComboboxSelected>>", self.mode_changed)
        b_adv = ttk.Button(op_row, text="詳細設定を開く", command=self.open_advanced)
        b_adv.pack(side="left", padx=5)
        self.controls.append(b_adv)

        self.controls.append(self.operation_box)
        self.option_container = ttk.Frame(main)
        self.option_container.pack(fill="x")
        self.option_frames = {}

        f_split = ttk.LabelFrame(self.option_container, text="分割設定", padding=8)
        e_chunk = ttk.Entry(f_split, textvariable=self.chunk_var, width=6)
        e_chunk.pack(side="left")
        ttk.Label(f_split, text="ページずつに分割し、ZIPへまとめる").pack(side="left", padx=5)
        self.option_frames["split"] = f_split
        self.controls.append(e_chunk)

        f_rotate = ttk.LabelFrame(self.option_container, text="回転設定", padding=8)
        cb_angle = ttk.Combobox(f_rotate, textvariable=self.angle_var, values=["右へ90°","左へ90°","180°","回転指定を0°にする"], state="readonly", width=22)
        cb_angle.pack(side="left")
        self.option_frames["rotate"] = f_rotate
        self.controls.append(cb_angle)

        f_opt = ttk.LabelFrame(self.option_container, text="最適化設定", padding=8)
        cb_lossy = ttk.Checkbutton(f_opt, text="画像の画質を落として容量を減らす（任意）", variable=self.lossy_var)
        cb_lossy.pack(anchor="w")
        cb_web = ttk.Checkbutton(f_opt, text="Webで開きやすい構造にする", variable=self.web_var)
        cb_web.pack(anchor="w")
        self.option_frames["optimize"] = f_opt
        self.controls.extend([cb_lossy, cb_web])

        f_prot = ttk.LabelFrame(self.option_container, text="パスワード設定", padding=8)
        r1 = ttk.Frame(f_prot); r1.pack(fill="x")
        ttk.Label(r1, text="設定するパスワード").pack(side="left")
        e_new_pass = ttk.Entry(r1, textvariable=self.open_password_var, show="*", width=20)
        e_new_pass.pack(side="left", padx=5)
        r2 = ttk.Frame(f_prot); r2.pack(fill="x")
        ttk.Label(r2, text="管理用（省略可）").pack(side="left")
        e_owner_pass = ttk.Entry(r2, textvariable=self.owner_password_var, show="*", width=20)
        e_owner_pass.pack(side="left", padx=5)
        self.option_frames["protect"] = f_prot
        self.controls.extend([e_new_pass, e_owner_pass])

        out_row = ttk.Frame(main); out_row.pack(fill="x", pady=10)
        self.output_frame=out_row
        ttk.Label(out_row, text="保存先").pack(side="left")
        e_out = ttk.Entry(out_row, textvariable=self.output_var)
        e_out.pack(side="left", fill="x", expand=True, padx=5)
        self.controls.append(e_out)
        b_pick = ttk.Button(out_row, text="保存先…", command=self.pick_output)
        b_pick.pack(side="left")
        self.controls.append(b_pick)

        act_row = ttk.Frame(main); act_row.pack(fill="x")
        self.start_button = ttk.Button(act_row, text="実行する", command=self.start)
        self.start_button.pack(side="left")
        self.controls.append(self.start_button)

        self.stop_button = ttk.Button(act_row, text="停止", command=self.stop, state="disabled")
        self.stop_button.pack(side="left", padx=5)

        b_open_out = ttk.Button(act_row, text="保存したファイルを開く", command=self.open_output)
        b_open_out.pack(side="left", padx=5)
        self.controls.append(b_open_out)

        b_help = ttk.Button(act_row, text="使い方", command=self.help)
        b_help.pack(side="right")

        self.progress = ttk.Progressbar(main, mode="indeterminate")
        self.progress.pack(fill="x", pady=5)

        ttk.Label(main, textvariable=self.status_var, wraplength=920).pack(anchor="w")

        self.log_text = tk.Text(main, height=7, wrap="word", state="disabled")
        self.log_text.pack(fill="both", expand=True, pady=5)

        ttk.Label(main, text="元のPDFは変更しません。既存ファイルを上書きせず、新しいファイルへ保存します。", style="Muted.TLabel").pack(anchor="w")

        self.mode_changed()

    def busy(self):return self.worker is not None
    def _values(self,row):return (Path(row['path']).name,row.get('pages') or 'すべて',row.get('count','—'),f"{Path(row['path']).stat().st_size/1024:.0f} KiB" if Path(row['path']).is_file() else '見つかりません')
    def render(self,index=0):
        self.current_row=None;self.tree.delete(*self.tree.get_children())
        for i,row in enumerate(self.rows):self.tree.insert('', 'end',iid=str(i),values=self._values(row))
        if self.rows:self.tree.selection_set(str(min(max(index,0),len(self.rows)-1)))
        else:self.page_var.set('');self.password_var.set('')
    def selection_changed(self,event=None):
        if self.current_row is not None and not self.busy():self.current_row.update(pages=self.page_var.get(),password=self.password_var.get())
        selected=self.tree.selection();self.current_row=self.rows[int(selected[0])] if selected else None
        if self.current_row is not None:self.page_var.set(self.current_row.get('pages',''));self.password_var.set(self.current_row.get('password',''))
    def save_fields(self):
        if self.busy() or self.current_row is None:return
        self.current_row.update(pages=self.page_var.get(),password=self.password_var.get())
        for i,row in enumerate(self.rows):self.tree.item(str(i),values=self._values(row))
    def add_paths(self,paths):
        if self.busy():return
        self.save_fields()
        for p in paths:
            if len(self.rows)>=50:break
            self.rows.append(dict(path=str(Path(p).resolve()),pages='',password=''))
        self.render();self.status_var.set(f'{len(self.rows)}件のPDFを追加しました。結合は一覧の順番で行います。')
        if self.rows and not self.output_var.get():self.output_var.set(str(Path(self.rows[0]['path']).parent/'まとめたPDF.pdf'))
    def add_files(self):self.add_paths(filedialog.askopenfilenames(filetypes=[('PDF','*.pdf')]))
    def remove_files(self):
        if self.busy():return
        self.save_fields();selected=self.tree.selection()
        if selected:self.rows.pop(int(selected[0]));self.render()
    def _move(self,delta):
        if self.busy():return
        self.save_fields();selected=self.tree.selection()
        if selected:
            old=int(selected[0]);new=old+delta
            if 0<=new<len(self.rows):self.rows[old],self.rows[new]=self.rows[new],self.rows[old];self.render(new)
    def move_up(self):self._move(-1)
    def move_down(self):self._move(1)
    def open_source(self):
        selected=self.tree.selection()
        if selected:
            p=Path(self.rows[int(selected[0])]['path'])
            if p.is_file():os.startfile(str(p))
    def options(self):return dict(chunk=self.chunk_var.get(),angle=ANGLES.get(self.angle_var.get()),lossy=self.lossy_var.get(),web=self.web_var.get(),open_password=self.open_password_var.get(),owner_password=self.owner_password_var.get(),advanced=self.advanced_json)
    def selected_rows(self,op):
        self.save_fields();selected=self.tree.selection()
        if not self.rows:raise ValueError('PDFを追加してください。')
        return copy.deepcopy(self.rows if op=='merge' else [self.rows[int(selected[0]) if selected else 0]])
    def kind(self):
        op=OP_LABELS[self.operation.get()]
        if op=='advanced':
            try:return build_job(self.selected_rows(op),op,self.options())[1]
            except Exception:return 'pdf'
        return 'zip' if op=='split' else 'report' if op=='check' else 'pdf'
    def mode_changed(self,event=None):
        op=OP_LABELS[self.operation.get()]
        for f in self.option_frames.values():f.pack_forget()
        self.option_container.pack_forget()
        if op in self.option_frames:
            self.option_container.pack(fill='x',before=self.output_frame)
            self.option_frames[op].pack(fill='x',pady=4)
        for w in self.controls:
            if isinstance(w,ttk.Entry) and w.cget('textvariable')==str(self.page_var):w.configure(state='normal' if op in ('merge','extract','split','rotate') and not self.busy() else 'disabled')
        if self.output_var.get():
            extension={'zip':'.zip','report':'.txt','json-report':'.json','json-file':'.json','binary':'.bin','predicate':'.txt','pdf':'.pdf'}[self.kind()]
            self.output_var.set(str(Path(self.output_var.get()).with_suffix(extension)))
    def pick_output(self):
        kind=self.kind();ext={'zip':'.zip','report':'.txt','json-report':'.json','json-file':'.json','binary':'.bin','predicate':'.txt','pdf':'.pdf'}[kind]
        target=Path(self.output_var.get()) if self.output_var.get() else None
        p=filedialog.asksaveasfilename(defaultextension=ext,filetypes=[('保存するファイル','*'+ext)],initialdir=str(target.parent) if target else None,initialfile=target.name if target else None)
        if p:self.output_var.set(p)
    def set_busy(self,value):
        if value:self.normal_states={w:w.cget('state') for w in self.controls}
        for w in self.controls:w.configure(state='disabled' if value else self.normal_states[w])
        self.stop_button.configure(state='normal' if value else 'disabled')
        if value:self.progress.start(12)
        else:self.progress.stop();self.mode_changed()
    def start(self):
        if self.busy():return
        try:
            op=OP_LABELS[self.operation.get()];rows=self.selected_rows(op);options=self.options();destination=self.output_var.get()
            if not destination:raise ValueError('保存先を指定してください。')
        except Exception as e:self.status_var.set(str(e));return
        self.launch(rows,op,destination,options)
    def count_pages(self):
        if self.busy():return
        try:rows=self.selected_rows('count')
        except ValueError as e:self.status_var.set(str(e));return
        self.pending_row=self.rows[int(self.tree.selection()[0])] if self.tree.selection() else self.rows[0]
        self.launch(rows,'count','',{})
    def launch(self,rows,op,destination,options):
        self.cancel.clear();self.set_busy(True);self.status_var.set('処理しています…');self._log('')
        def work():
            try:self.q.put(('done',(op,run_job(rows,op,destination,options,self.cancel))))
            except InterruptedError:self.q.put(('error','停止しました。元のPDFと既存ファイルは変更していません。'))
            except Exception as e:self.q.put(('error',str(e)))
        self.worker=threading.Thread(target=work,daemon=True);self.worker.start()
    def stop(self):self.cancel.set();self.status_var.set('停止しています…')
    def _log(self,text):self.log_text.configure(state='normal');self.log_text.delete('1.0','end');self.log_text.insert('1.0',text[:65536]);self.log_text.configure(state='disabled')
    def poll(self):
        while True:
            try:kind,value=self.q.get_nowait()
            except queue.Empty:break
            if kind=='error':self.status_var.set(value);self._log(value)
            else:
                op,result=value
                if op=='count':
                    try:
                        count=int(result['data'].decode().strip());self.pending_row['count']=count
                        for i,r in enumerate(self.rows):self.tree.item(str(i),values=self._values(r))
                        self.status_var.set(f'{count}ページのPDFです。')
                    except Exception:self.status_var.set('ページ数を確認できませんでした。')
                    self.pending_row=None
                else:
                    self.last_output=result['output'];self.status_var.set(f"保存しました: {Path(result['output']).name}（{result['size']/1024:.1f} KiB）"+(' / 警告があります。記録をご確認ください。' if result['warning'] else ''))
                text=result['data'].decode('utf8',errors='replace') if result['kind'] in ('report','json-report','predicate') else ''
                self._log(text+'\n'+result['log'])
        if self.worker and not self.worker.is_alive():self.worker.join();self.worker=None;self.set_busy(False)
        if self.closing and not self.busy():self.destroy();return
        self.after(100,self.poll)
    def close(self):
        self.closing=True;self.cancel.set()
        if not self.busy():self.destroy()
        else:self.status_var.set('処理を停止して終了しています…')
    def open_output(self):
        p=Path(self.last_output)
        if self.last_output and p.is_file() and p.suffix.lower() in ('.pdf','.txt','.json','.zip'):os.startfile(str(p))
    def help(self):
        win=tk.Toplevel(self);win.title('使い方');win.geometry('790x540');text=tk.Text(win,wrap='word',padx=12,pady=10);text.pack(fill='both',expand=True)
        text.insert('1.0','PDFを追加して順番を決め、操作と保存先を選んで実行します。\n結合は一覧のPDFすべて、ほかの操作は選択した1件が対象です。\nページ欄は結合・取り出し・分割・回転に使います。空欄はすべて、1,3-5や5-1で指定できます。\n入力PDFのパスワードはPDFごとに設定できます。\n通常のPDF出力には元PDFのパスワード設定を引き継ぎます。解除したい場合は「パスワードを解除」を選びます。\n分割はZIPへまとめます。容量の最適化で必ず小さくなるとは限りません。\n1件200 MiB、合計500 MiB、50件まで。出力300 MiB、処理180秒、分割500件まで。\nMicrosoft Visual C++ v14（x64）が必要です。\nhttps://learn.microsoft.com/en-us/cpp/windows/latest-supported-vc-redist\n文章の直接編集・OCRには対応していません。加工すると電子署名が無効になる場合があります。\n\n同梱エンジンのヘルプ:\n'+Path(resource_path('upstream-help.txt',Path(__file__).parent)).read_text(encoding='utf8'));text.configure(state='disabled')
    def open_advanced(self):
        win=tk.Toplevel(self);win.title('詳細設定');win.geometry('820x590');frame=ttk.Frame(win,padding=10);frame.pack(fill='both',expand=True)
        ttk.Label(frame,text='元ツールの追加機能をJob JSONで指定します。保存先はメイン画面で管理します。').pack(anchor='w')
        examples={'設定なし':{},'PDFを上に重ねる':{'overlay':[{'file':'','to':'1-z','repeat':'1'}]},'PDFを下に重ねる':{'underlay':[{'file':'','to':'1-z','repeat':'1'}]},'ファイルを添付する':{'addAttachment':[{'file':''}]},'添付ファイル一覧':{'listAttachments':''},'注釈を固定する':{'flattenAnnotations':'all','generateAppearances':''},'文書の作成情報を削除':{'removeInfo':'','removeMetadata':''},'構造をJSONで確認':{'json':'2'},'JSON形式で書き出す':{'jsonOutput':'2'},'Web用に並べ直す':{'linearize':''},'ページ構造を確認':{'showPages':'','withImages':''}}
        bar=ttk.Frame(frame);bar.pack(fill='x',pady=6);preset=tk.StringVar(value='設定なし');combo=ttk.Combobox(bar,textvariable=preset,values=list(examples),state='readonly',width=24);combo.pack(side='left')
        text=tk.Text(frame,wrap='none',height=11);text.pack(fill='both',expand=True);text.insert('1.0',self.advanced_json)
        def example(event=None):
            value=copy.deepcopy(examples[preset.get()])
            for key in ('overlay','underlay','addAttachment'):
                if key in value:
                    p=filedialog.askopenfilename(parent=win,filetypes=[('参照ファイル','*.*')])
                    if not p:return
                    value[key][0]['file']=str(Path(p).resolve())
            text.delete('1.0','end');text.insert('1.0',json.dumps(value,ensure_ascii=False,indent=2))
        combo.bind('<<ComboboxSelected>>',example)
        def apply():
            try:
                value=json.loads(text.get('1.0','end'));validate_extra(value);self.advanced_json=json.dumps(value,ensure_ascii=False);self.operation.set('詳細設定');self.mode_changed();win.destroy()
            except Exception as e:messagebox.showerror('設定を確認してください',str(e),parent=win)
        ttk.Button(bar,text='この設定を使う',command=apply).pack(side='right')
        ttk.Label(frame,text='使えるキーと値（説明）:').pack(anchor='w',pady=(9,3));schema=tk.Text(frame,wrap='word',height=10);schema.pack(fill='both',expand=True);schema.insert('1.0',Path(resource_path('job-schema.json',Path(__file__).parent)).read_text(encoding='utf8'));schema.configure(state='disabled')
        ttk.Label(frame,text='元ファイルへの上書き・外部ジョブの読み込み・外部ストリーム出力・弱い暗号化は使用できません。').pack(anchor='w',pady=(7,0))
if __name__=='__main__':App().mainloop()
