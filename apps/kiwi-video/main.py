"""A local video conversion workbench for everyday use."""
import base64,os,queue,threading,tkinter as tk
from pathlib import Path
from tkinter import ttk,filedialog,messagebox
import engine
from options import DEFAULTS,validate
CHOICES={"mode":{"動画を変換・軽量化":"video","音声だけを保存":"audio","静止画を保存":"frame"},"codec":{"MP4 / H.264（おすすめ）":"h264","MP4 / H.265":"hevc","WebM / VP9":"vp9"},"resolution":{"元のサイズ（偶数へ調整）":0,"フルHDの枠内":1920,"HDの枠内（おすすめ）":1280,"480pの枠内":854,"360pの枠内":640},"audio_format":{"MP3":"mp3","M4A / AAC":"m4a","WAV（無圧縮）":"wav","FLAC（可逆圧縮）":"flac","Opus":"opus"},"frame_format":{"PNG":"png","JPEG":"jpg"}}
class App(tk.Tk):
 def __init__(self):
  super().__init__();self.title("きうい動画工房");self.geometry("1120x820");self.minsize(1040,760)
  self.paths=[];self.results=[];self.photo=None;self.busy=False;self.closing=False;self.events=queue.Queue();self.cancel=threading.Event();self.controls=[]
  self.vars={k:tk.BooleanVar(value=v) if type(v) is bool else tk.StringVar(value=str(v)) for k,v in DEFAULTS.items()}
  for k,mapping in CHOICES.items():self.vars[k].set(next(label for label,value in mapping.items() if value==DEFAULTS[k]))
  self.status=tk.StringVar(value="動画を選び、やりたいことと保存設定を選んでください。")
  p=ttk.Frame(self,padding=14);p.pack(fill="both",expand=True)
  ttk.Label(p,text="きうい動画工房",font=("Yu Gothic UI",20,"bold")).pack(anchor="w")
  ttk.Label(p,text="動画を小さく、必要な区間だけ、音声だけに。元ファイルを残して保存します。").pack(anchor="w",pady=(3,9))
  bar=ttk.Frame(p);bar.pack(fill="x")
  self.button(bar,"動画・音声を選ぶ（F4）",self.pick).pack(side="left")
  self.button(bar,"選択をクリア",self.clear).pack(side="left",padx=8)
  self.button(bar,"動画エンジンを準備（初回約87MB）",self.prepare).pack(side="right")
  self.engine_status=ttk.Label(p,text="エンジン："+("準備済み" if engine.installed() else "初回の準備が必要です"));self.engine_status.pack(anchor="e")
  self.files=tk.Listbox(p,height=3,exportselection=False);self.files.pack(fill="x",pady=(3,8));self.controls.append(self.files)
  row=ttk.Frame(p);row.pack(fill="both",expand=True)
  left=ttk.Frame(row);left.pack(side="left",fill="both",expand=True,padx=(0,14))
  self.preview_label=ttk.Label(left,text="開始位置の映像をここに表示します。",anchor="center");self.preview_label.pack(fill="both",expand=True)
  self.info=tk.StringVar(value="ファイルの情報は「情報・プレビュー」で確認できます。")
  ttk.Label(left,textvariable=self.info,wraplength=450,justify="left").pack(anchor="w",pady=12)
  ttk.Label(left,text="プレビューは大きさ・向きの確認用です。\n圧縮後の画質・音は、保存したファイルで確認してください。",wraplength=450).pack(anchor="w",pady=8)
  right=ttk.Notebook(row);right.pack(side="right",fill="both",expand=True)
  video=ttk.Frame(right,padding=10);clip=ttk.Frame(right,padding=10);audio=ttk.Frame(right,padding=10)
  for frame,title in [(video,"保存・画質"),(clip,"区間・映像"),(audio,"音声")]:right.add(frame,text=title)
  self.field(video,"mode","やりたいこと",list(CHOICES["mode"]))
  self.field(video,"codec","動画の保存形式",list(CHOICES["codec"]))
  self.field(video,"resolution","動画のサイズ",list(CHOICES["resolution"]))
  self.field(video,"quality","画質値（18：高画質～35：小さく）")
  presets=ttk.Frame(video);presets.pack(fill="x",pady=8)
  for name,q in [("画質重視",18),("バランス",23),("容量重視",28)]:self.button(presets,name,lambda q=q:self.vars["quality"].set(str(q))).pack(side="left",padx=3)
  self.field(video,"fps","フレームレート（0：元と同じ）",["0","24","25","30","50","60"])
  self.field(video,"frame_format","静止画の形式",list(CHOICES["frame_format"]))
  self.tick(video,"strip","撮影情報などのメタデータをコピーしない")
  ttk.Label(video,text="動画は再圧縮します。容量が増える場合もあります。\nH.264が互換性重視のおすすめです。\nH.265・VP9は再生環境により非対応の場合があります。\nサイズ変更は縦横比を保ち、小さい動画を拡大しません。",wraplength=460).pack(anchor="w",pady=10)
  self.field(clip,"start","開始（秒・小数可）");self.field(clip,"end","終了（秒・0なら最後まで）")
  ttk.Label(clip,text="静止画は開始位置の1コマを保存します。\n終了位置は動画・音声の切り出しに使います。").pack(anchor="w",pady=4)
  self.field(clip,"rotate","時計回りの回転",["0","90","180","270"])
  self.tick(clip,"flip","上下を反転");self.tick(clip,"flop","左右を反転")
  self.tick(clip,"crop","映像を切り抜く（自動回転後・偶数で指定）")
  for k,label in [("x","左から（px）"),("y","上から（px）"),("width","切り抜く幅（px）"),("height","切り抜く高さ（px）")]:self.field(clip,k,label)
  self.field(audio,"audio_format","音声だけ保存する形式",list(CHOICES["audio_format"]))
  self.field(audio,"audio_track","音声トラック（先頭は0）")
  self.field(audio,"audio_kbps","音声ビットレート（64～320kbps）")
  self.field(audio,"volume","音量（0～200%）")
  self.tick(audio,"normalize","音量のばらつきを整える（目安 -16 LUFS）")
  self.tick(audio,"mute","動画の音を消す（音声だけ保存には適用しません）")
  ttk.Label(audio,text="音声は48kHz・ステレオに変換します。\nWAV・FLACにはビットレート指定を使いません。\nWAV・FLACへの変換で元の非可逆音声が復元することはありません。\n字幕・追加映像・チャプターは引き継ぎません。",wraplength=440).pack(anchor="w",pady=14)
  buttons=ttk.Frame(p);buttons.pack(fill="x",pady=10)
  self.button(buttons,"情報・プレビュー（F6）",self.preview).pack(side="left")
  self.button(buttons,"設定を戻す",self.reset).pack(side="left",padx=8)
  self.button(buttons,"別名で保存（F5）",self.save).pack(side="left")
  self.stop=ttk.Button(buttons,text="停止",command=self.cancel.set,state="disabled");self.stop.pack(side="left",padx=8)
  self.button(buttons,"保存先を開く",self.open_output).pack(side="right")
  self.progress=ttk.Progressbar(p,mode="indeterminate");self.progress.pack(fill="x",pady=(0,6))
  self.table=ttk.Treeview(p,columns=("name","before","after"),show="headings",height=2)
  for k,title,width in [("name","保存したファイル",560),("before","元のサイズ",160),("after","保存サイズ",160)]:self.table.heading(k,text=title);self.table.column(k,width=width)
  self.table.pack(fill="x");ttk.Label(p,textvariable=self.status,wraplength=1060).pack(anchor="w",pady=(7,0))
  self.bind("<F4>",lambda _:self.pick());self.bind("<F5>",lambda _:self.save());self.bind("<F6>",lambda _:self.preview())
  self.protocol("WM_DELETE_WINDOW",self.close);self.after(100,self.poll)
 def button(self,parent,text,fn):
  b=ttk.Button(parent,text=text,command=fn);self.controls.append(b);return b
 def field(self,parent,key,label,choices=None):
  row=ttk.Frame(parent);row.pack(fill="x",pady=5);ttk.Label(row,text=label).pack(side="left")
  w=ttk.Combobox(row,textvariable=self.vars[key],values=choices,state="readonly",width=23 if key in CHOICES else 12) if choices else ttk.Entry(row,textvariable=self.vars[key],width=12)
  w.pack(side="right");self.controls.append(w)
 def tick(self,parent,key,label):
  w=ttk.Checkbutton(parent,text=label,variable=self.vars[key]);w.pack(anchor="w",pady=4);self.controls.append(w)
 def settings(self):
  raw={k:v.get() for k,v in self.vars.items()}
  for k,default in DEFAULTS.items():
   if k in CHOICES:raw[k]=CHOICES[k][raw[k]]
   elif type(default) is int:
    if not str(raw[k]).isdigit():raise ValueError("数値欄は0以上の整数で指定してください。")
    raw[k]=int(raw[k])
   elif type(default) is float:raw[k]=float(raw[k])
  return validate(raw)
 def reset(self):
  if self.busy:return
  for k,v in DEFAULTS.items():self.vars[k].set(next(label for label,value in CHOICES[k].items() if value==v) if k in CHOICES else v)
  self.status.set("設定を初期値に戻しました。")
 def pick(self):
  if self.busy:return
  paths=filedialog.askopenfilenames(parent=self,title="動画・音声を選ぶ（5件まで）",filetypes=[("動画・音声","*.mp4 *.m4v *.mov *.mkv *.webm *.avi *.mpg *.mpeg *.ts *.mp3 *.m4a *.wav *.flac *.ogg *.opus")])
  if not paths:return
  if len(paths)>5:messagebox.showerror("選択件数","5件まで選べます。",parent=self);return
  self.paths=list(paths);self.files.delete(0,"end")
  for p in paths:self.files.insert("end",Path(p).name)
  self.files.selection_set(0);self.photo=None;self.preview_label.configure(image="",text="「情報・プレビュー」で開始位置を確認できます。");self.status.set(f"{len(paths)}件を選びました。")
 def clear(self):
  if self.busy:return
  self.paths=[];self.files.delete(0,"end");self.photo=None;self.preview_label.configure(image="",text="開始位置の映像をここに表示します。");self.info.set("")
 def job(self,kind,fn):
  if self.busy:return
  self.busy=True;self.cancel.clear();self.status.set("処理中です。長い動画は時間がかかります。")
  for w in self.controls:w.configure(state="disabled")
  self.stop.configure(state="normal");self.progress.start(12)
  def worker():
   try:self.events.put((kind,fn()))
   except engine.Cancelled:self.events.put(("notice","停止しました。すでに保存したファイルは残ります。"))
   except Exception as exc:self.events.put(("error",str(exc)))
   finally:self.events.put(("done",None))
  threading.Thread(target=worker,daemon=True).start()
 def prepare(self):
  if self.busy:return
  if engine.installed():self.status.set("動画エンジンは準備済みです。");return
  if not messagebox.askokcancel("動画エンジンの準備","FFmpeg公式サイトが案内するBtbNのGitHubから約87MBを取得します。初回のみ通信し、動画・音声は送信しません。展開後は約225MBを使います。続けますか？",parent=self):return
  self.job("installed",lambda:engine.install(self.cancel,lambda s:self.events.put(("notice",s))))
 def preview(self):
  if self.busy:return
  try:
   if not self.paths:raise ValueError("ファイルを選んでください。")
   v=self.settings();path=self.paths[(self.files.curselection() or (0,))[0]]
  except Exception as exc:messagebox.showerror("設定の確認",str(exc),parent=self);return
  self.job("preview",lambda:(None,engine.inspect(path,self.cancel)) if v["mode"]=="audio" else engine.convert(path,v,None,self.cancel,True))
 def save(self):
  if self.busy:return
  try:
   if not self.paths:raise ValueError("ファイルを選んでください。")
   v=self.settings()
  except Exception as exc:messagebox.showerror("設定の確認",str(exc),parent=self);return
  directory=filedialog.askdirectory(parent=self,title="保存先を選ぶ（既存ファイルは上書きしません）")
  if not directory:return
  self.table.delete(*self.table.get_children());self.results=[];paths=list(self.paths)
  def work():
   for i,path in enumerate(paths):
    self.events.put(("notice",f"{i+1}/{len(paths)}件目を変換しています…"))
    item=engine.convert(path,v,directory,self.cancel);self.events.put(("item",item))
   return len(paths)
  self.job("saved",work)
 def open_output(self):
  if self.results:os.startfile(str(Path(self.results[-1]["output"]).parent))
 def poll(self):
  try:
   while True:
    kind,value=self.events.get_nowait()
    if kind=="done":
     self.busy=False;self.progress.stop()
     if self.closing:self.destroy();return
     for w in self.controls:w.configure(state="readonly" if isinstance(w,ttk.Combobox) else "normal")
     self.stop.configure(state="disabled")
    elif kind=="preview":
     data,info=value;video=info["video"];tracks=" / ".join(f"{i}: {s.get('codec_name','?')} {s.get('tags',{}).get('language','')}" for i,s in enumerate(info["audios"]))
     self.info.set(f"長さ：{info['duration']:.2f}秒\n"+(f"映像：{video['display_width']}×{video['display_height']} / {video['fps']:.2f}fps / {video.get('codec_name','')}\n" if video else "映像なし\n")+"音声："+(tracks[:250] if tracks else "なし"))
     if data:
      self.photo=tk.PhotoImage(data=base64.b64encode(data).decode("ascii"),format="png")
      self.preview_label.configure(image=self.photo,text="")
     else:self.photo=None;self.preview_label.configure(image="",text="音声の情報を確認できます。")
     self.status.set("情報を読み取りました。プレビューは開始位置の映像です。")
    elif kind=="item":
     self.results.append(value);self.table.insert("","end",values=(Path(value["output"]).name,f"{value['before']/1024**2:.2f} MiB",f"{value['after']/1024**2:.2f} MiB"))
    elif kind=="saved":self.status.set(f"{value}件を保存しました。元ファイルは変更していません。")
    elif kind=="notice":self.status.set(value)
    elif kind=="installed":self.engine_status.configure(text="エンジン：準備済み");self.status.set("準備できました。動画・音声の処理はPC内で行います。")
    elif kind=="error":
     self.status.set(value[:200])
     if not self.closing:messagebox.showerror("完了できませんでした",value,parent=self)
  except queue.Empty:pass
  self.after(100,self.poll)
 def close(self):
  if self.busy:self.closing=True;self.cancel.set();self.status.set("停止処理を待っています…")
  else:self.destroy()
if __name__=="__main__":App().mainloop()
