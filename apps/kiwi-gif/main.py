"""Arrange images, create GIFs and preview the result."""
import os,queue,re,threading,tkinter as tk
from tkinter import ttk,filedialog,messagebox
from pathlib import Path
from PIL import Image,ImageOps,ImageTk
import runner
from options import COLORS
KINDS={'画像を並べる':'images','既存GIFを変換':'gif','Y4Mを変換（詳細）':'y4m'}
class App(tk.Tk):
 def __init__(self):
  super().__init__();self.title('きういGIF工房');self.geometry('1120x900');self.minsize(1060,850)
  self.paths=[];self.worker=None;self.cancel=threading.Event();self.events=queue.Queue();self.closing=False;self.preview=None;self.photo=None;self.preview_frames=1;self.preview_index=0;self.playing=False;self.after_preview=None;self.output=None
  self.kind=tk.StringVar(value='画像を並べる');self.status=tk.StringVar(value='画像を2枚以上追加し、並べてGIFにできます。');self.result=tk.StringVar(value='作成結果をここで確認できます。')
  self.vars={k:tk.StringVar(value=v) for k,v in dict(fps='5',quality='90',width='640',height='0',repeat='0',speed='1',mode='標準',fit='余白で合わせる',background='透明',motion='',lossy='',matte='',fixed='',space='').items()};self.bounce=tk.BooleanVar()
  outer=ttk.Frame(self,padding=14);outer.pack(fill='both',expand=True)
  ttk.Label(outer,text='きういGIF工房',font=('Yu Gothic UI',21,'bold')).pack(anchor='w')
  ttk.Label(outer,text='写真やイラストを、動くGIFに。元ファイルを残して、PC内で作成します。').pack(anchor='w',pady=(2,10))
  row=ttk.Frame(outer);row.pack(fill='x');ttk.Label(row,text='入力方法').pack(side='left');ttk.Combobox(row,textvariable=self.kind,values=list(KINDS),state='readonly',width=24).pack(side='left',padx=8)
  ttk.Button(row,text='ファイルを追加（F4）',command=self.add_files).pack(side='left');ttk.Button(row,text='一覧を空にする',command=self.clear).pack(side='left',padx=8)
  body=ttk.Frame(outer);body.pack(fill='both',pady=8);left=ttk.Frame(body);left.pack(side='left',fill='both',expand=True);right=ttk.Frame(body,width=450);right.pack(side='left',fill='both',padx=(12,0))
  self.listbox=tk.Listbox(left,height=10,selectmode='extended',exportselection=False,font=('Yu Gothic UI',10));self.listbox.pack(fill='both',expand=True);self.listbox.bind('<<ListboxSelect>>',self.selected)
  buttons=ttk.Frame(left);buttons.pack(fill='x',pady=5)
  for text,cmd in [('上へ',lambda:self.move(-1)),('下へ',lambda:self.move(1)),('名前順',self.sort),('選択を外す',self.remove)]:ttk.Button(buttons,text=text,command=cmd,width=12).pack(side='left',padx=(0,5))
  self.preview_label=ttk.Label(right,text='画像・作成GIFのプレビュー',anchor='center',width=58);self.preview_label.pack(fill='both',expand=True);ttk.Button(right,text='プレビュー 再生 / 停止',command=self.toggle_play).pack(pady=4)
  ttk.Label(outer,textvariable=self.result).pack(anchor='w')
  settings=ttk.LabelFrame(outer,text='GIFの仕上がり',padding=10);settings.pack(fill='x',pady=9)
  for r,items in enumerate([
   [('FPS（画像・Y4M）','fps',.1,100),('品質 1～100','quality',1,100),('最大幅 px（0＝自動）','width',0,1600),('高さ px（0＝自動）','height',0,1600)],
   [('繰り返し（-1＝1回、0＝無限）','repeat',-1,32767),('速度倍率（GIF・Y4M）','speed',.01,1000)]
  ]):
   f=ttk.Frame(settings);f.pack(fill='x',pady=3)
   for text,key,low,high in items:ttk.Label(f,text=text).pack(side='left');ttk.Spinbox(f,textvariable=self.vars[key],from_=low,to=high,width=6).pack(side='left',padx=(5,12))
  f=ttk.Frame(settings);f.pack(fill='x',pady=4)
  for text,key,values in [('処理','mode',['標準','速度優先','仕上がり優先']),('画像のサイズ合わせ','fit',['余白で合わせる','切り抜いて合わせる']),('余白の背景','background',['透明','白','黒'])]:ttk.Label(f,text=text).pack(side='left');ttk.Combobox(f,textvariable=self.vars[key],values=values,state='readonly',width=18).pack(side='left',padx=(5,10))
  ttk.Checkbutton(f,text='往復再生（画像のみ）',variable=self.bounce).pack(side='left')
  ttk.Label(settings,text='幅と高さを両方指定すると縦横比が変わる場合があります。FPSが50を超えるとブラウザーで指定どおり再生されない場合があります。').pack(anchor='w',pady=(4,0))
  advanced=ttk.LabelFrame(outer,text='詳細調整（空欄は元ツールの標準設定）',padding=10);advanced.pack(fill='x')
  f=ttk.Frame(advanced);f.pack(fill='x')
  for text,key,width in [('動きの品質 1～100','motion',5),('圧縮の品質 1～100','lossy',5),('半透明の背景色 HEX','matte',9)]:ttk.Label(f,text=text).pack(side='left');ttk.Entry(f,textvariable=self.vars[key],width=width).pack(side='left',padx=(5,12))
  f=ttk.Frame(advanced);f.pack(fill='x',pady=(7,0));ttk.Label(f,text='固定色 HEX（16色まで、カンマ区切り）').pack(side='left');ttk.Entry(f,textvariable=self.vars['fixed'],width=38).pack(side='left',padx=5);ttk.Label(f,text='Y4M色空間').pack(side='left',padx=(10,3));ttk.Combobox(f,textvariable=self.vars['space'],values=COLORS,state='readonly',width=11).pack(side='left')
  ttk.Label(outer,text='画像は最初の1フレームを使います。既存GIFの再圧縮は画質が落ちる場合があります。MP4などの動画は読み込みません。').pack(anchor='w',pady=(9,2))
  ttk.Label(outer,text='画像2～100枚・各25 MiB、GIF/Y4Mは300フレームまで。入力合計256 MiB・1億2,000万画素、作成は5分まで。').pack(anchor='w')
  actions=ttk.Frame(outer);actions.pack(fill='x',pady=9);ttk.Button(actions,text='保存名を選んでGIFを作る（F5）',command=self.start_export).pack(side='left');self.stop=ttk.Button(actions,text='停止',command=self.cancel.set,state='disabled');self.stop.pack(side='left',padx=8);ttk.Button(actions,text='保存先フォルダーを開く',command=self.open_output).pack(side='left')
  self.progress=ttk.Progressbar(outer,mode='indeterminate');self.progress.pack(fill='x');ttk.Label(outer,textvariable=self.status).pack(anchor='w',pady=5)
  self.log=tk.Text(outer,height=5,wrap='word',font=('Yu Gothic UI',10));self.log.pack(fill='both',expand=True)
  foot=ttk.Frame(outer);foot.pack(fill='x',pady=(7,0));ttk.Button(foot,text='結果をコピー',command=self.copy).pack(side='left');ttk.Button(foot,text='結果をTXT保存',command=self.save_log).pack(side='left',padx=7);ttk.Label(foot,text='gifskiを利用した非公式GUI · 0.1.0').pack(side='right')
  self.bind('<F4>',lambda event:self.add_files());self.bind('<F5>',lambda event:self.start_export())
  self.protocol('WM_DELETE_WINDOW',self.close);self.after(70,self.poll)
 def refresh(self):
  self.listbox.delete(0,'end')
  for i,p in enumerate(self.paths):self.listbox.insert('end',f'{i+1:03d}  {Path(p).name}')
 def add_files(self):
  if self.worker is not None:return
  values=filedialog.askopenfilenames(parent=self,title='GIFに使う画像・GIF・Y4M')
  for p in values:
   if p not in self.paths:self.paths.append(p)
  if len(self.paths)>100:del self.paths[100:];messagebox.showinfo('画像数','100枚までです。',parent=self)
  self.refresh()
 def clear(self):
  if self.worker is None:self.paths.clear();self.refresh()
 def remove(self):
  if self.worker is not None:return
  for i in reversed(self.listbox.curselection()):del self.paths[i]
  self.refresh()
 def sort(self):
  if self.worker is None:self.paths.sort(key=lambda p:[int(x) if x.isdigit() else x.casefold() for x in re.split(r'(\d+)',Path(p).name)]);self.refresh()
 def move(self,delta):
  if self.worker is not None:return
  indexes=list(self.listbox.curselection())
  if len(indexes)!=1:return
  i=indexes[0];j=i+delta
  if 0<=j<len(self.paths):self.paths[i],self.paths[j]=self.paths[j],self.paths[i];self.refresh();self.listbox.selection_set(j)
 def selected(self,event=None):
  if self.worker is not None:return
  indexes=self.listbox.curselection()
  if len(indexes)!=1:return
  p=Path(self.paths[indexes[0]])
  if p.suffix.lower()=='.y4m':self.result.set('Y4Mの入力プレビューはありません。作成したGIFは確認できます。');return
  try:self.load_preview(p,1);self.result.set('入力画像：'+p.name+'（最初のフレーム）')
  except Exception:self.result.set('このファイルはプレビューできません。入力を確認してください。')
 def stop_preview(self):
  self.playing=False
  if self.after_preview:
   try:self.after_cancel(self.after_preview)
   except tk.TclError:pass
   self.after_preview=None
  if self.preview:self.preview.close();self.preview=None
  self.photo=None;self.preview_label.config(image='',text='画像・作成GIFのプレビュー')
 def load_preview(self,p,count):
  self.stop_preview()
  if Path(p).stat().st_size>runner.INPUT_LIMIT:raise ValueError('画像が大きすぎます。')
  self.preview=Image.open(p)
  if self.preview.format not in ('PNG','JPEG','WEBP','BMP','GIF','TIFF'):self.stop_preview();raise ValueError('対応する画像を選んでください。')
  if self.preview.width*self.preview.height>12000000:self.stop_preview();raise ValueError('画像が大きすぎます。')
  self.preview_frames=count;self.preview_index=0;self.render_frame()
 def render_frame(self):
  if not self.preview:return
  try:
   self.preview.seek(self.preview_index);frame=ImageOps.exif_transpose(self.preview).convert('RGBA');frame.thumbnail((440,240),Image.Resampling.LANCZOS);self.photo=ImageTk.PhotoImage(frame);self.preview_label.config(image=self.photo,text='')
   delay=max(20,min(600000,int(self.preview.info.get('duration',100))))
   if self.playing:self.preview_index=(self.preview_index+1)%self.preview_frames;self.after_preview=self.after(delay,self.render_frame)
  except Exception:self.playing=False
 def toggle_play(self):
  if not self.preview or self.preview_frames<2:return
  self.playing=not self.playing
  if self.after_preview:self.after_cancel(self.after_preview);self.after_preview=None
  if self.playing:self.render_frame()
 def start_export(self):
  if self.worker is not None:return
  try:
   kind=KINDS[self.kind.get()];o={k:v.get() for k,v in self.vars.items()};o.update(mode={'標準':'normal','速度優先':'fast','仕上がり優先':'extra'}[o['mode']],fit={'余白で合わせる':'contain','切り抜いて合わせる':'crop'}[o['fit']],background={'透明':'transparent','白':'white','黒':'black'}[o['background']],bounce=self.bounce.get());runner.validate(o,kind)
   values=list(self.paths)
   if (kind=='images' and not 2<=len(values)<=100) or (kind!='images' and len(values)!=1):raise ValueError('画像は2枚以上、GIF・Y4Mは1件にしてください。')
   dest=filedialog.asksaveasfilename(parent=self,title='新しいGIFの保存名',initialfile='アニメーション.gif',defaultextension='.gif',filetypes=[('GIF','*.gif')])
   if not dest:return
   self.cancel.clear();self.output=None;self.log.delete('1.0','end');self.stop.config(state='normal');self.status.set('GIFを作成しています…');self.progress.start(15)
   def job():
    try:r=runner.export(values,dest,o,kind,self.cancel,lambda i,n:self.events.put(('progress',i,n)));self.events.put(('done',dest,r))
    except Exception as e:self.events.put(('error',str(e),None))
   self.worker=threading.Thread(target=job,daemon=False);self.worker.start()
  except Exception as e:messagebox.showerror('入力の確認',str(e),parent=self)
 def poll(self):
  try:
   while True:
    kind,value,r=self.events.get_nowait()
    if kind=='progress':self.status.set(f'画像を準備しています… {value} / {r}');continue
    self.worker.join(timeout=1);self.worker=None;self.progress.stop();self.stop.config(state='disabled')
    if kind=='done':
     self.output=Path(value);self.status.set('作成しました。');text=f'{self.output.name}\n{r["width"]} × {r["height"]} px / {r["frames"]}フレーム / {r["duration"]/1000:.2f}秒 / {r["bytes"]/1024:.1f} KiB';self.log.insert('end',text);self.result.set(text.replace('\n','  '))
     if not self.closing:
      try:self.load_preview(self.output,r['frames'])
      except Exception:self.result.set('GIFを保存しました。プレビューできませんでした。')
    else:self.status.set('停止しました。' if self.cancel.is_set() else '作成できませんでした。結果欄を確認してください。');self.log.insert('end',value)
  except queue.Empty:pass
  if self.closing and self.worker is None:self.destroy();return
  self.after(70,self.poll)
 def copy(self):
  text=self.log.get('1.0','end-1c')
  if text:self.clipboard_clear();self.clipboard_append(text)
 def save_log(self):
  text=self.log.get('1.0','end-1c')
  if not text:return
  p=filedialog.asksaveasfilename(parent=self,initialfile='GIF作成結果.txt',defaultextension='.txt')
  if p:
   try:
    with open(p,'x',encoding='utf8') as f:f.write(text)
   except Exception as e:messagebox.showerror('保存できません',str(e),parent=self)
 def open_output(self):
  if self.output and self.output.parent.is_dir():os.startfile(self.output.parent)
 def close(self):self.closing=True;self.cancel.set();self.stop_preview();self.status.set('処理を停止しています…')
if __name__=='__main__':App().mainloop()
