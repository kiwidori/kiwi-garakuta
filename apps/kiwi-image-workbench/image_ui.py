"""Batch photo conversion and adjustment for Windows."""
import io,json,os,queue,threading,tkinter as tk
from tkinter import ttk,filedialog,messagebox
from pathlib import Path
from PIL import Image,ImageTk
import image_engine as engine
from image_options import validate

MODES={"変更しない":"none","枠内に収める":"fit","中央で切り抜く":"fill","縦横を指定":"exact","倍率で指定":"percent"}
BACKGROUNDS={"白":"white","黒":"black","透明":"transparent"}
DEFAULTS={"format":"JPEG","quality":85,"size_mode":"none","width":1024,"height":1024,"percent":100,"upscale":False,"rotate":0,"flip":False,"flop":False,"crop_enabled":False,"x":0,"y":0,"crop_width":100,"crop_height":100,"grayscale":False,"brightness":0,"contrast":0,"saturation":100,"gamma":1.0,"sharpen":0.0,"blur":0.0,"normalize":False,"negate":False,"sepia":0,"strip":False,"progressive":False,"lossless":False,"background":"white"}
class App(tk.Tk):
 def __init__(self):
  super().__init__();self.title("きうい画像工房");self.geometry("1120x820");self.minsize(1040,760)
  self.worker=None;self.paths=[];self.results=[];self.busy=False;self.closing=False;self.cancel=threading.Event();self.events=queue.Queue();self.controls=[];self.photos=[]
  self.vars={k:tk.BooleanVar(value=v) if isinstance(v,bool) else tk.StringVar(value=str(v)) for k,v in DEFAULTS.items()}
  self.vars["size_mode"].set("変更しない");self.vars["background"].set("白")
  self.status=tk.StringVar(value="画像を選び、保存する形式やサイズを指定してください。")
  p=ttk.Frame(self,padding=14);p.pack(fill="both",expand=True)
  ttk.Label(p,text="きうい画像工房",font=("Yu Gothic UI",20,"bold")).pack(anchor="w")
  ttk.Label(p,text="写真をまとめて変換・リサイズ。元画像を残して、新しいファイルに保存します。").pack(anchor="w",pady=(2,8))
  top=ttk.Frame(p);top.pack(fill="x")
  self.button(top,"画像を選ぶ（F4）",self.pick).pack(side="left")
  self.button(top,"選択をクリア",self.clear).pack(side="left",padx=8)
  self.button(top,"画像エンジンを準備（初回約12MB）",self.prepare).pack(side="right")
  self.engine_status=ttk.Label(p,text="画像エンジン："+("準備済み" if engine.installed() else "初回の準備が必要です"));self.engine_status.pack(anchor="e")
  self.files=tk.Listbox(p,height=3,exportselection=False);self.files.pack(fill="x",pady=(3,8));self.controls.append(self.files)
  row=ttk.Frame(p);row.pack(fill="both",expand=True)
  left=ttk.Frame(row);left.pack(side="left",fill="both",expand=True,padx=(0,12))
  self.original=ttk.Label(left,text="元画像",anchor="center");self.original.pack(fill="both",expand=True)
  self.changed=ttk.Label(left,text="変換後のプレビュー",anchor="center");self.changed.pack(fill="both",expand=True)
  ttk.Label(left,text="JPEGなどの圧縮も反映します。プレビューは縮小表示です。",wraplength=440).pack(anchor="w")
  right=ttk.Notebook(row);right.pack(side="right",fill="both",expand=True)
  one=ttk.Frame(right,padding=10);two=ttk.Frame(right,padding=10);three=ttk.Frame(right,padding=10)
  for frame,title in [(one,"サイズ・保存"),(two,"切り抜き・向き"),(three,"色・仕上げ")]:right.add(frame,text=title)
  self.field(one,"format","保存形式",["JPEG","PNG","WEBP","AVIF","BMP","TIFF","GIF","ICO"])
  self.field(one,"quality","画質（1～100）")
  self.field(one,"size_mode","サイズ指定",list(MODES))
  ttk.Label(one,text="枠内：縦横比を保ち、指定した枠に収めます。\n中央切り抜き：指定した枠いっぱいにします。\n縦横指定：縦横比が変わる場合があります。",justify="left").pack(anchor="w",pady=3)
  self.field(one,"width","幅（1～8,000px）");self.field(one,"height","高さ（1～8,000px）");self.field(one,"percent","倍率（1～400%）")
  self.tick(one,"upscale","小さい画像の拡大を許可（fillでは必須）")
  self.field(one,"background","透明部分の背景",list(BACKGROUNDS))
  self.tick(one,"strip","位置情報などのメタデータを削除")
  self.tick(one,"progressive","JPEGを徐々に表示する形式にする")
  self.tick(one,"lossless","WebPを可逆圧縮にする")
  ttk.Label(one,text="JPEGは透明非対応（白／黒に合成）。\nICOは最大256px。GIF・TIFFは先頭の1枚です。",wraplength=420).pack(anchor="w",pady=7)
  self.tick(two,"crop_enabled","切り抜きを使う（自動回転後の座標）")
  for k,label in [("x","左から（px）"),("y","上から（px）"),("crop_width","切り抜く幅（px）"),("crop_height","切り抜く高さ（px）")]:self.field(two,k,label)
  self.field(two,"rotate","時計回りに回転",["0","90","180","270"])
  self.tick(two,"flip","上下を反転");self.tick(two,"flop","左右を反転")
  ttk.Label(two,text="写真の撮影方向を自動で補正したあと、\n切り抜き → サイズ → 回転・反転の順に処理します。").pack(anchor="w",pady=12)
  for k,label in [("brightness","明るさ（-100～100）"),("contrast","コントラスト（-100～100）"),("saturation","鮮やかさ（0～200）"),("gamma","ガンマ（0.1～5）"),("sharpen","シャープ（0～5）"),("blur","ぼかし（0～5）"),("sepia","セピア（0～100%）")]:self.field(three,k,label)
  self.tick(three,"grayscale","モノクロにする");self.tick(three,"normalize","明暗の範囲を自動で広げる");self.tick(three,"negate","色を反転する")
  bottom=ttk.Frame(p);bottom.pack(fill="x",pady=10)
  self.button(bottom,"プレビュー（F6）",self.preview).pack(side="left")
  self.button(bottom,"設定を戻す",self.reset).pack(side="left",padx=8)
  self.button(bottom,"すべて別名で保存（F5）",self.save).pack(side="left")
  self.stop=ttk.Button(bottom,text="停止",command=self.cancel.set,state="disabled");self.stop.pack(side="left",padx=8)
  self.button(bottom,"保存先を開く",self.open_output).pack(side="right")
  self.table=ttk.Treeview(p,columns=("name","before","after"),show="headings",height=3)
  for key,title,width in [("name","保存した画像",570),("before","元のサイズ",150),("after","保存サイズ",150)]:self.table.heading(key,text=title);self.table.column(key,width=width)
  self.table.pack(fill="x");ttk.Label(p,textvariable=self.status,wraplength=1060).pack(anchor="w",pady=(7,0))
  self.bind("<F4>",lambda _:self.pick());self.bind("<F5>",lambda _:self.save());self.bind("<F6>",lambda _:self.preview())
  self.protocol("WM_DELETE_WINDOW",self.close);self.after(100,self.poll)
 def button(self,parent,text,command):
  b=ttk.Button(parent,text=text,command=command);self.controls.append(b);return b
 def field(self,parent,key,label,choices=None):
  row=ttk.Frame(parent);row.pack(fill="x",pady=3);ttk.Label(row,text=label,width=27).pack(side="left")
  widget=ttk.Combobox(row,textvariable=self.vars[key],values=choices,state="readonly",width=13) if choices else ttk.Entry(row,textvariable=self.vars[key],width=15)
  widget.pack(side="right");self.controls.append(widget)
 def tick(self,parent,key,label):
  w=ttk.Checkbutton(parent,text=label,variable=self.vars[key]);w.pack(anchor="w",pady=3);self.controls.append(w)
 def settings(self):
  raw={k:v.get() for k,v in self.vars.items()}
  raw["size_mode"]=MODES[raw["size_mode"]];raw["background"]=BACKGROUNDS[raw["background"]]
  for k,default in DEFAULTS.items():
   if isinstance(default,bool):continue
   if isinstance(default,int):
    value=str(raw[k]).strip()
    if not value or not value.lstrip("-").isdigit():raise ValueError("数値欄は整数で指定してください。")
    raw[k]=int(value)
   elif isinstance(default,float):raw[k]=float(raw[k])
  return validate(raw)
 def reset(self):
  if self.busy:return
  for k,v in DEFAULTS.items():self.vars[k].set(v)
  self.vars["size_mode"].set("変更しない");self.vars["background"].set("白")
  self.status.set("設定を初期値に戻しました。")
 def pick(self):
  if self.busy:return
  values=filedialog.askopenfilenames(parent=self,title="画像を選ぶ（20枚まで）",filetypes=[("画像","*.jpg *.jpeg *.png *.webp *.avif *.heic *.heif *.bmp *.tif *.tiff *.gif")])
  if not values:return
  if len(values)>20:messagebox.showerror("選択枚数","20枚まで選べます。",parent=self);return
  self.paths=list(values);self.files.delete(0,"end")
  for p in self.paths:self.files.insert("end",Path(p).name)
  self.files.selection_set(0);self.status.set(f"{len(values)}枚を選びました。プレビューで仕上がりを確認できます。")
 def clear(self):
  if self.busy:return
  self.paths=[];self.files.delete(0,"end");self.photos=[];self.original.configure(image="",text="元画像");self.changed.configure(image="",text="変換後のプレビュー")
 def job(self,kind,fn):
  if self.busy:return
  self.busy=True;self.cancel.clear();self.status.set("処理中です…")
  for w in self.controls:w.configure(state="disabled")
  self.stop.configure(state="normal")
  def worker():
   try:self.events.put((kind,fn()))
   except engine.Cancelled:self.events.put(("notice","停止しました。保存済みの画像は残ります。"))
   except Exception as exc:self.events.put(("error",str(exc)))
   finally:self.events.put(("done",None))
  self.worker=threading.Thread(target=worker,daemon=False);self.worker.start()
 def prepare(self):
  if self.busy:return
  if engine.installed():self.status.set("画像エンジンは準備済みです。");return
  if not messagebox.askokcancel("画像エンジンの準備","ImageMagick公式GitHubから約12MBをダウンロードします。初回のみ通信し、画像は送信しません。続けますか？",parent=self):return
  self.job("installed",lambda:engine.install(self.cancel,lambda s:self.events.put(("notice",s))))
 def preview(self):
  if self.busy:return
  try:
   if not self.paths:raise ValueError("画像を選んでください。")
   opts=self.settings();idx=(self.files.curselection() or (0,))[0];path=self.paths[idx]
  except Exception as exc:messagebox.showerror("設定の確認",str(exc),parent=self);return
  self.job("preview",lambda:(engine.transform(path,DEFAULTS,self.cancel,True),engine.transform(path,opts,self.cancel,True)))
 def save(self):
  if self.busy:return
  try:
   if not self.paths:raise ValueError("画像を選んでください。")
   opts=self.settings()
  except Exception as exc:messagebox.showerror("設定の確認",str(exc),parent=self);return
  directory=filedialog.askdirectory(parent=self,title="保存先を選ぶ（元の画像は変更しません）")
  if directory:
   self.table.delete(*self.table.get_children());self.results=[]
   self.job("saved",lambda:engine.batch(self.paths,opts,directory,self.cancel,lambda item:self.events.put(("item",item))))
 def open_output(self):
  if self.results:os.startfile(str(Path(self.results[-1]["output"]).parent))
 def poll(self):
  try:
   while True:
    kind,value=self.events.get_nowait()
    if kind=="done":
     self.busy=False
     if self.closing:self.destroy();return
     for w in self.controls:w.configure(state="readonly" if isinstance(w,ttk.Combobox) else "normal")
     self.stop.configure(state="disabled")
    elif kind=="preview":
     self.photos=[]
     for target,data in zip((self.original,self.changed),value):
      with Image.open(io.BytesIO(data)) as im:
       im.thumbnail((460,200));photo=ImageTk.PhotoImage(im.copy())
      self.photos.append(photo);target.configure(image=photo,text="")
     self.status.set("上：元画像 / 下：変換後。保存する前に設定を確認してください。")
    elif kind=="installed":self.engine_status.configure(text="画像エンジン：準備済み");self.status.set("準備できました。次回からは通信せずに画像を処理できます。")
    elif kind=="item":
     self.results.append(value);self.table.insert("","end",values=(Path(value["output"]).name,f"{value['before']/1024:,.1f} KiB",f"{value['after']/1024:,.1f} KiB"));self.status.set(f"{len(self.results)}枚を保存しました。")
    elif kind=="saved":self.status.set(f"{len(value)}枚を保存しました。元画像は変更していません。")
    elif kind=="notice":self.status.set(value)
    elif kind=="error":
     self.status.set(value[:200])
     if not self.closing:messagebox.showerror("処理を完了できませんでした",value,parent=self)
  except queue.Empty:pass
  self.after(100,self.poll)
 def close(self):
  if self.busy:self.closing=True;self.cancel.set();self.status.set("停止処理を待っています…")
  else:self.destroy()
if __name__=="__main__":App().mainloop()
