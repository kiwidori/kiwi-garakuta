"""An offline image enlargement window."""
import os,queue,sys,threading,tkinter as tk
from pathlib import Path
from tkinter import ttk,filedialog,messagebox
if not getattr(sys,'frozen',False):sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'common'))
from PIL import Image,ImageOps,ImageTk
from runtime import resource_path
from core import MODELS,gather_folder,run_batch

class App(tk.Tk):
    def __init__(self):
        super().__init__();self.title('きうい画像拡大');self.geometry('1050x770');self.minsize(900,690)
        self.paths=[];self.results={};self.photos=[];self.q=queue.Queue();self.cancel=threading.Event();self.worker=None;self.closing=False
        self.destination=tk.StringVar();self.model=tk.StringVar(value=list(MODELS)[0]);self.scale=tk.StringVar(value='4');self.format=tk.StringVar(value='png')
        self.tile=tk.StringVar(value='64');self.gpu=tk.StringVar(value='auto');self.threads=tk.StringVar(value='1:1:1');self.tta=tk.BooleanVar();self.verbose=tk.BooleanVar()
        self.status=tk.StringVar(value='画像を追加してください。画像はこのPCの中だけで処理します。');self.widgets=[]
        self._build();self.protocol('WM_DELETE_WINDOW',self.close);self.after(100,self.poll)
    def _build(self):
        style=ttk.Style(self);style.configure('TButton',padding=5);style.configure('Title.TLabel',font=('Yu Gothic UI',18,'bold'));style.configure('TLabel',font=('Yu Gothic UI',10))
        root=ttk.Frame(self,padding=14);root.pack(fill='both',expand=True)
        ttk.Label(root,text='小さな画像を、見やすい大きさに。',style='Title.TLabel').pack(anchor='w')
        ttk.Label(root,text='写真・イラストを拡大して別ファイルへ保存。元画像と見比べながら選べます。').pack(anchor='w',pady=(0,9))
        bar=ttk.Frame(root);bar.pack(fill='x')
        for text,cmd in [('画像を追加',self.add_files),('フォルダーから追加',self.add_folder),('選択を外す',self.remove),('すべて外す',self.clear)]:
            w=ttk.Button(bar,text=text,command=cmd);w.pack(side='left',padx=(0,5));self.widgets.append(w)
        self.tree=ttk.Treeview(root,columns=('name','state','size'),show='headings',height=5,selectmode='extended')
        for key,text,width in [('name','画像',430),('state','処理結果',260),('size','大きさ',240)]:self.tree.heading(key,text=text);self.tree.column(key,width=width)
        self.tree.pack(fill='x',pady=8);self.tree.bind('<<TreeviewSelect>>',lambda e:self.preview())
        dest=ttk.Frame(root);dest.pack(fill='x',pady=4);ttk.Label(dest,text='保存フォルダー').pack(side='left',padx=(0,8))
        w=ttk.Entry(dest,textvariable=self.destination);w.pack(side='left',fill='x',expand=True);self.widgets.append(w)
        w=ttk.Button(dest,text='選択…',command=self.pick_destination);w.pack(side='left',padx=5);self.widgets.append(w)
        opts=ttk.Frame(root);opts.pack(fill='x',pady=5)
        for label,var,vals,width in [('画像の種類',self.model,list(MODELS),23),('倍率',self.scale,['2','3','4'],4),('保存形式',self.format,['png','jpg','webp'],6)]:
            ttk.Label(opts,text=label).pack(side='left',padx=(0,5));w=ttk.Combobox(opts,textvariable=var,values=vals,state='readonly',width=width);w.pack(side='left',padx=(0,16));self.widgets.append(w)
            if var is self.model:w.bind('<<ComboboxSelected>>',lambda e:self.model_changed())
            if var is self.scale:self.scale_box=w
        advanced=ttk.LabelFrame(root,text='細かな設定（困っていなければそのままでOK）',padding=6);advanced.pack(fill='x',pady=4)
        for text,var,values,width in [('タイル（0=自動）',self.tile,['0','32','64','128','256'],6),('GPU（auto=自動）',self.gpu,['auto',*map(str,range(8))],6),('スレッド 読込:処理:保存',self.threads,['1:1:1','1:2:2','2:2:2','4:4:4'],8)]:
            ttk.Label(advanced,text=text).pack(side='left',padx=(0,3));w=ttk.Combobox(advanced,textvariable=var,values=values,width=width,state='normal' if var in (self.tile,self.threads) else 'readonly');w.pack(side='left',padx=(0,9));self.widgets.append(w)
        for text,var in [('じっくり処理（TTA）',self.tta),('詳しい記録',self.verbose)]:
            w=ttk.Checkbutton(advanced,text=text,variable=var);w.pack(side='left',padx=3);self.widgets.append(w)
        actions=ttk.Frame(root);actions.pack(fill='x',pady=7)
        self.start_button=ttk.Button(actions,text='拡大する',command=self.start);self.start_button.pack(side='left');self.widgets.append(self.start_button)
        self.stop_button=ttk.Button(actions,text='停止',command=self.cancel.set,state='disabled');self.stop_button.pack(side='left',padx=7)
        ttk.Button(actions,text='保存フォルダーを開く',command=self.open_destination).pack(side='left',padx=5)
        ttk.Button(actions,text='選択画像の記録',command=self.show_record).pack(side='left',padx=5)
        ttk.Button(actions,text='使い方・必要なもの',command=self.help).pack(side='right')
        self.progress=ttk.Progressbar(root,mode='determinate');self.progress.pack(fill='x')
        ttk.Label(root,textvariable=self.status,wraplength=970).pack(anchor='w',pady=5)
        previews=ttk.Frame(root);previews.pack(fill='both',expand=True)
        self.before=ttk.LabelFrame(previews,text='元画像',padding=5);self.before.pack(side='left',fill='both',expand=True,padx=(0,5))
        self.after_frame=ttk.LabelFrame(previews,text='拡大した画像',padding=5);self.after_frame.pack(side='left',fill='both',expand=True)
        self.before_label=ttk.Label(self.before,anchor='center');self.before_label.pack(fill='both',expand=True)
        self.after_label=ttk.Label(self.after_frame,anchor='center');self.after_label.pack(fill='both',expand=True)
        ttk.Label(root,text='Vulkan対応GPUが必要です。推測した細部を補うため、顔や文字が元の姿と異なる場合があります。',foreground='#555',wraplength=970).pack(anchor='w',pady=(7,0))
        self.model_changed()
    def busy(self):return self.worker is not None
    def model_changed(self):
        allowed=['2','3','4'] if MODELS[self.model.get()]=='realesr-animevideov3' else ['4']
        self.scale_box.configure(values=allowed)
        if self.scale.get() not in allowed:self.scale.set('4')
    def add(self,paths):
        if self.busy():return
        current={str(Path(p).resolve()).casefold() for p in self.paths}
        for p in paths:
            p=str(Path(p).resolve());key=p.casefold()
            if key not in current and len(self.paths)<50:self.paths.append(p);current.add(key)
        self.results={};self.render();self.status.set(f'{len(self.paths)}枚を選択。最大50枚です。')
        if self.paths and not self.destination.get():self.destination.set(str(Path(self.paths[0]).parent/'拡大した画像'))
    def add_files(self):self.add(filedialog.askopenfilenames(filetypes=[('画像','*.png *.jpg *.jpeg *.webp')]))
    def add_folder(self):
        p=filedialog.askdirectory()
        if p:
            try:self.add(gather_folder(p))
            except Exception as e:self.status.set(str(e))
    def remove(self):
        if self.busy():return
        selected={int(i) for i in self.tree.selection()};self.paths=[p for i,p in enumerate(self.paths) if i not in selected];self.results={};self.render()
    def clear(self):
        if not self.busy():self.paths=[];self.results={};self.render()
    def pick_destination(self):
        p=filedialog.askdirectory()
        if p:self.destination.set(p)
    def render(self):
        selected=self.tree.selection();self.tree.delete(*self.tree.get_children())
        for i,p in enumerate(self.paths):
            r=self.results.get(p,{})
            dims=r.get('size','');state={'completed':'完了','failed':'失敗','skipped':'スキップ'}.get(r.get('status'),r.get('status','待機'))
            self.tree.insert('', 'end',iid=str(i),values=(Path(p).name,state,dims))
        if selected and self.tree.exists(selected[0]):self.tree.selection_set(selected[0])
        elif self.paths:self.tree.selection_set('0')
        self.preview()
    def preview(self):
        self.photos=[];self.before_label.configure(image='',text='');self.after_label.configure(image='',text='')
        selected=self.tree.selection()
        if not selected:return
        p=self.paths[int(selected[0])];r=self.results.get(p,{})
        for label,frame,path,resample in [(self.before_label,self.before,p,Image.Resampling.BILINEAR),(self.after_label,self.after_frame,r.get('output'),Image.Resampling.LANCZOS)]:
            if not path:label.configure(text=r.get('error','まだ処理していません'),wraplength=450);continue
            try:
                with Image.open(path) as src:
                    if src.width*src.height>64_000_000:raise ValueError('プレビューの画像が大きすぎます。')
                    im=ImageOps.exif_transpose(src).convert('RGBA');dimensions=im.size
                    factor=min(450/im.width,200/im.height);im=im.resize((max(1,int(im.width*factor)),max(1,int(im.height*factor))),resample)
                photo=ImageTk.PhotoImage(im);self.photos.append(photo);label.configure(image=photo);frame.configure(text=('元画像' if label is self.before_label else '拡大した画像')+f'  {dimensions[0]} × {dimensions[1]} px')
            except Exception as e:label.configure(text='画像を表示できません: '+str(e),wraplength=440)
    def set_busy(self,value):
        if value:self.normal_states={w:w.cget('state') for w in self.widgets}
        for w in self.widgets:w.configure(state='disabled' if value else self.normal_states[w])
        self.stop_button.configure(state='normal' if value else 'disabled')
    def start(self):
        if self.busy():return
        paths=list(self.paths);dest=self.destination.get()
        try:settings=dict(model=self.model.get(),scale=int(self.scale.get()),format=self.format.get(),tile=int(self.tile.get()),gpu='auto' if self.gpu.get()=='auto' else int(self.gpu.get()),threads=self.threads.get(),tta=self.tta.get(),verbose=self.verbose.get())
        except ValueError:self.status.set('倍率・タイル・GPU番号は整数で指定してください。');return
        if not paths or not dest:self.status.set('画像と保存フォルダーを選んでください。');return
        self.cancel.clear();self.results={};self.progress.configure(maximum=len(paths),value=0);self.set_busy(True);self.status.set('拡大しています… 大きな画像やじっくり処理は時間がかかります。')
        def work():
            try:
                results=run_batch(paths,dest,settings,self.cancel,lambda r:self.q.put(('image',r)))
                counts={k:sum(r['status']==k for r in results) for k in ('completed','failed','skipped')}
                self.q.put(('done',f"完了: 成功 {counts['completed']}枚 / スキップ {counts['skipped']}枚 / 失敗 {counts['failed']}枚。画像を選ぶと結果を確認できます。"))
            except InterruptedError:self.q.put(('done','停止しました。処理済みの画像は残っています。'))
            except Exception as e:self.q.put(('done',str(e)))
        self.worker=threading.Thread(target=work,daemon=True);self.worker.start()
    def poll(self):
        while True:
            try:kind,value=self.q.get_nowait()
            except queue.Empty:break
            if kind=='image':
                self.results[value['source']]=value;self.progress.configure(value=len(self.results));self.render()
            else:self.status.set(value)
        if self.worker and not self.worker.is_alive():self.worker.join();self.worker=None;self.set_busy(False)
        if self.closing and not self.busy():self.destroy();return
        self.after(100,self.poll)
    def close(self):
        self.closing=True;self.cancel.set()
        if not self.busy():self.destroy()
        else:self.status.set('処理を停止して終了しています…')
    def open_destination(self):
        p=Path(self.destination.get())
        if self.destination.get() and p.is_dir():os.startfile(str(p.resolve()))
        else:self.status.set('保存フォルダーがまだありません。')
    def show_record(self):
        selected=self.tree.selection()
        if not selected:return
        p=self.paths[int(selected[0])];r=self.results.get(p,{})
        win=tk.Toplevel(self);win.title('選択画像の記録');win.geometry('750x410');text=tk.Text(win,wrap='word',padx=10,pady=8);text.pack(fill='both',expand=True)
        text.insert('1.0',Path(p).name+'\n'+str(r.get('size',''))+'\n'+r.get('error','')+'\n'+r.get('log','まだ記録はありません。'));text.configure(state='disabled')
    def help(self):
        win=tk.Toplevel(self);win.title('使い方・必要なもの');win.geometry('750x510');text=tk.Text(win,wrap='word',padx=12,pady=10);text.pack(fill='both',expand=True)
        text.insert('1.0','写真とイラストは4倍、軽量イラストは2・3・4倍です。\nPNG/JPEG/WebPの静止画像を最大50枚、1枚400万画素まで扱えます。\n保存先に同名の画像がある場合はスキップします。\n元画像を残し、撮影情報を除いて新しい画像を保存します。\nVulkan対応GPU・GPUドライバーとMicrosoft Visual C++ v14 (x64)が必要です。\nhttps://learn.microsoft.com/en-us/cpp/windows/latest-supported-vc-redist\n1枚180秒で停止。タイムアウト時は小さい画像や軽量イラストをお試しください。\n\n細かな設定: タイルを小さくするとGPUメモリ使用量を抑えられます。\nGPU番号とスレッドは元ツールの設定です。TTAは処理時間が増えます。\nJPEGの透過部分は白背景になります。16bit/HDR画像には対応していません。\n推測で細部を補うので、文字や顔の正確な復元には使えません。\n\n同梱エンジンのヘルプ:\n'+Path(resource_path('upstream-help.txt',Path(__file__).parent)).read_text(encoding='utf8'));text.configure(state='disabled')
if __name__=='__main__':App().mainloop()
