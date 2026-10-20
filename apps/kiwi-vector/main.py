"""A small desktop image tracing workbench."""
import os
from pathlib import Path
import queue
import tempfile
import threading
import tkinter as tk
from tkinter import filedialog,messagebox,ttk
import webbrowser
from PIL import Image,ImageTk
import engine
from options import PRESETS,validate

CHOICES={'colormode':{'カラー':'color','白黒':'bw'},'hierarchical':{'重ねる':'stacked','くり抜く':'cutout'},
         'mode':{'なめらかな曲線':'spline','多角形':'polygon','ピクセルの輪郭':'pixel'},
         'background':{'白にする':'white','透明部分を使う（カラー）':'original'}}
NUMBERS=[('filter_speckle','小さな点を除く',0,16),('color_precision','色の精度',1,8),
         ('gradient_step','色のまとめ具合',0,255),('corner_threshold','角の判定（度）',0,180),
         ('segment_length','線分の長さ',3.5,10),('splice_threshold','曲線を分ける角度',0,180),
         ('path_precision','座標の小数桁数',0,8)]


class App(tk.Tk):
    def __init__(self):
        super().__init__();self.title('きういベクター工房');self.geometry('1140x830');self.minsize(1000,760)
        self.paths=[];self.outputs=[];self.busy=False;self.closing=False;self.photo=None
        self.cancel=threading.Event();self.events=queue.Queue();self.controls=[]
        self.preview_dir=tempfile.TemporaryDirectory(prefix='kiwi-vector-preview-')
        self.status=tk.StringVar(value='ロゴ・線画・イラストなどを選んでください。');self.preset=tk.StringVar(value='イラスト')
        self.vars={key:tk.StringVar() for key in [*CHOICES,*[n[0] for n in NUMBERS]]}
        p=ttk.Frame(self,padding=14);p.pack(fill='both',expand=True)
        ttk.Label(p,text='きういベクター工房',font=('Yu Gothic UI',19,'bold')).pack(anchor='w')
        ttk.Label(p,text='ロゴやイラストの輪郭をなぞって、拡大に強いSVGへ。元画像は変更しません。').pack(anchor='w',pady=(3,9))
        bar=ttk.Frame(p);bar.pack(fill='x')
        self.button(bar,'画像を選ぶ（F4）',self.pick).pack(side='left')
        self.button(bar,'選択をクリア',self.clear).pack(side='left',padx=8)
        self.count=ttk.Label(bar,text='未選択');self.count.pack(side='left',padx=8)
        self.files=tk.Listbox(p,height=3,exportselection=False);self.files.pack(fill='x',pady=8)
        self.files.bind('<<ListboxSelect>>',lambda _:self.preview_input());self.controls.append(self.files)
        work=ttk.Frame(p);work.pack(fill='both',expand=True)
        left=ttk.LabelFrame(work,text='元画像',padding=8);left.pack(side='left',fill='both',expand=True,padx=(0,12))
        self.preview=ttk.Label(left,text='選んだ画像をここに表示します。',anchor='center');self.preview.pack(fill='both',expand=True)
        self.image_info=tk.StringVar();ttk.Label(left,textvariable=self.image_info,wraplength=390).pack(anchor='w',pady=7)
        ttk.Label(left,text='GIF・TIFFは先頭の1枚を使います。写真の細部を復元する機能ではありません。',wraplength=390).pack(anchor='w')
        right=ttk.Frame(work);right.pack(side='left',fill='both',expand=True)
        r=ttk.Frame(right);r.pack(fill='x',pady=(0,9))
        ttk.Label(r,text='おすすめ設定').pack(side='left')
        c=ttk.Combobox(r,textvariable=self.preset,values=list(PRESETS),state='readonly',width=12);c.pack(side='left',padx=8);self.controls.append(c)
        self.button(r,'設定を適用',self.apply_preset).pack(side='left')
        form=ttk.Frame(right);form.pack(fill='x')
        labels={'colormode':'色','hierarchical':'形の重なり方','mode':'輪郭の形','background':'背景'}
        for row,(key,choices) in enumerate(CHOICES.items()):
            ttk.Label(form,text=labels[key]).grid(row=row,column=0,sticky='w',pady=4)
            c=ttk.Combobox(form,textvariable=self.vars[key],values=list(choices),state='readonly',width=24);c.grid(row=row,column=1,sticky='ew',padx=8);self.controls.append(c)
        for row,(key,label,low,high) in enumerate(NUMBERS,4):
            ttk.Label(form,text=label).grid(row=row,column=0,sticky='w',pady=4)
            box=ttk.Spinbox(form,textvariable=self.vars[key],from_=low,to=high,increment=.5 if key=='segment_length' else 1,width=12)
            box.grid(row=row,column=1,sticky='w',padx=8);self.controls.append(box)
            ttk.Label(form,text=f'{low}～{high}').grid(row=row,column=2,sticky='w')
        form.columnconfigure(1,weight=1)
        ttk.Label(right,text='色の精度を下げると少ない色へ、色のまとめ具合を上げるとグラデーションを大きくまとめます。半透明は白に合成します。',wraplength=540).pack(anchor='w',pady=9)
        r=ttk.Frame(right);r.pack(fill='x',pady=(3,9))
        self.button(r,'選んだ1枚をSVG保存（F5）',lambda:self.convert(False)).pack(side='left')
        self.button(r,'すべて一括保存…',lambda:self.convert(True)).pack(side='left',padx=7)
        ttk.Label(right,text='SVGの確認',font=('Yu Gothic UI',11,'bold')).pack(anchor='w')
        self.result=ttk.Treeview(right,columns=('size','paths'),show='tree headings',height=4,selectmode='browse')
        self.result.heading('#0',text='ファイル');self.result.column('#0',width=210,minwidth=120)
        self.result.heading('size',text='容量');self.result.column('size',width=85,minwidth=65)
        self.result.heading('paths',text='輪郭数');self.result.column('paths',width=80,minwidth=65)
        self.result.pack(fill='both',expand=True,pady=5)
        r=ttk.Frame(right);r.pack(fill='x')
        self.button(r,'SVGをブラウザで見る',self.open_preview).pack(side='left')
        self.button(r,'SVGをコピー',self.copy_svg).pack(side='left',padx=6)
        self.button(r,'保存先を開く',self.open_folder).pack(side='left')
        r=ttk.Frame(p);r.pack(fill='x',pady=(10,3))
        self.stop=ttk.Button(r,text='停止',command=self.cancel.set,state='disabled');self.stop.pack(side='left')
        ttk.Label(r,text='1～20枚、各128 MiB・800万画素まで。変換はPC内で行います。').pack(side='left',padx=9)
        ttk.Label(p,textvariable=self.status,wraplength=1080).pack(anchor='w')
        self.apply_preset();self.bind('<F4>',lambda _:self.pick());self.bind('<F5>',lambda _:self.convert(False))
        self.protocol('WM_DELETE_WINDOW',self.close);self.after(80,self.poll)

    def button(self,parent,label,command):
        b=ttk.Button(parent,text=label,command=command);self.controls.append(b);return b

    def apply_preset(self):
        if self.busy:return
        for key,value in {**PRESETS[self.preset.get()],'background':'white'}.items():
            if key in CHOICES:
                self.vars[key].set(next(label for label,v in CHOICES[key].items() if v==value))
            else:self.vars[key].set(str(value))

    def options(self):
        return validate({key:CHOICES[key][var.get()] if key in CHOICES else var.get() for key,var in self.vars.items()})

    def pick(self):
        if self.busy:return
        paths=filedialog.askopenfilenames(parent=self,filetypes=[('画像','*.png *.jpg *.jpeg *.webp *.bmp *.tif *.tiff *.gif'),('すべて','*.*')])
        if not paths:return
        if len(paths)>20:messagebox.showerror('選択できません','最大20枚です。',parent=self);return
        self.paths=list(paths);self.files.delete(0,'end')
        for path in paths:self.files.insert('end',Path(path).name)
        self.files.selection_set(0);self.count.configure(text=f'{len(paths)}枚');self.preview_input()

    def clear(self):
        if self.busy:return
        self.paths=[];self.files.delete(0,'end');self.count.configure(text='未選択');self.preview.configure(image='',text='選んだ画像をここに表示します。');self.photo=None;self.image_info.set('')

    def selected_input(self):
        indices=self.files.curselection();return self.paths[indices[0] if indices else 0] if self.paths else None

    def preview_input(self):
        if self.busy or not self.paths:return
        try:
            path=self.selected_input();im=engine.load_image(path);width,height=im.size
            im.thumbnail((410,415),Image.Resampling.LANCZOS)
            bg=Image.new('RGBA',im.size,'white');bg.alpha_composite(im)
            self.photo=ImageTk.PhotoImage(bg.convert('RGB'));self.preview.configure(image=self.photo,text='')
            self.image_info.set(f'{Path(path).name}\n{width} × {height} px')
        except Exception as exc:
            self.preview.configure(image='',text='プレビューできません。');self.photo=None;self.status.set(str(exc))

    def convert(self,batch):
        if self.busy:return
        try:
            options=self.options()
            paths=list(self.paths) if batch else [self.selected_input()]
            if not paths or paths[0] is None:raise ValueError('画像を選んでください。')
        except Exception as exc:messagebox.showerror('設定を確認してください',str(exc),parent=self);return
        destination=filedialog.askdirectory(parent=self,title='一括保存先の親フォルダー') if batch else filedialog.asksaveasfilename(parent=self,initialfile=Path(paths[0]).stem+'.svg',defaultextension='.svg',filetypes=[('SVG','*.svg')])
        if not destination:return
        self.busy=True;self.cancel.clear();self.status.set('変換中…')
        for w in self.controls:w.configure(state='disabled')
        self.stop.configure(state='normal')
        def worker():
            try:self.events.put(('done',engine.convert(paths,destination,options,self.cancel,batch,lambda text:self.events.put(('progress',text)))))
            except Exception as exc:self.events.put(('error',str(exc)))
        threading.Thread(target=worker,daemon=True).start()

    def poll(self):
        try:
            while True:
                kind,value=self.events.get_nowait()
                if kind=='progress':self.status.set(value);continue
                self.busy=False
                for w in self.controls:w.configure(state='normal')
                for w in self.controls:
                    if isinstance(w,ttk.Combobox):w.configure(state='readonly')
                self.stop.configure(state='disabled')
                if kind=='done':
                    final,items=value;self.result.delete(*self.result.get_children());self.outputs=[]
                    for i,item in enumerate(items):
                        path=final/item['name'] if final.is_dir() else final;self.outputs.append(path)
                        self.result.insert('','end',iid=str(i),text=path.name,values=(f'{item["bytes"]/1024:.1f} KiB',item['paths']))
                    self.result.selection_set('0');self.status.set(f'{len(items)}枚を保存しました。SVGはブラウザで拡大して確認できます。')
                else:
                    self.status.set(value)
                    if not self.closing:messagebox.showerror('変換できません',value,parent=self)
        except queue.Empty:pass
        if self.closing and not self.busy:self.preview_dir.cleanup();self.destroy();return
        self.after(80,self.poll)

    def selected_output(self):
        selected=self.result.selection()
        if not selected:return None
        return engine.safe_path(self.outputs[int(selected[0])])

    def open_preview(self):
        path=self.selected_output()
        if path is None:return
        try:
            _,clean=engine.inspect_svg(path)
            target=Path(self.preview_dir.name)/(os.urandom(6).hex()+'.svg');target.write_bytes(clean)
            webbrowser.open(target.as_uri())
        except Exception as exc:messagebox.showerror('表示できません',str(exc),parent=self)

    def copy_svg(self):
        path=self.selected_output()
        if path is None:return
        try:
            _,clean=engine.inspect_svg(path)
            if len(clean)>1024**2:raise ValueError('1 MiBを超えるSVGはファイルとして利用してください。')
            self.clipboard_clear();self.clipboard_append(clean.decode('utf8'));self.status.set('SVGをコピーしました。')
        except Exception as exc:messagebox.showerror('コピーできません',str(exc),parent=self)

    def open_folder(self):
        path=self.selected_output()
        if path is not None and path.parent.is_dir():os.startfile(path.parent)

    def close(self):self.closing=True;self.cancel.set()


if __name__=='__main__':App().mainloop()
