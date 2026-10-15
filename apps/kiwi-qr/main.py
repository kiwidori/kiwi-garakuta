"""Create QR codes and read local barcode images."""
import base64,io,json,multiprocessing,os,secrets,sys,threading,time,queue,tkinter as tk
from pathlib import Path
from tkinter import ttk,filedialog,messagebox,colorchooser
from PIL import Image,ImageTk
import jobs

STYLES={'四角':'square','角にすき間':'gapped','丸':'circle','角丸':'rounded','縦の線':'vertical','横の線':'horizontal'}
GRADIENTS={'単色':'solid','中央から外':'radial','四角い広がり':'square','左から右':'horizontal','上から下':'vertical'}
KINDS=('QRコード','Code128','EAN13','EAN8','UPCA','UPCE','Code39','Code93','Codabar','Code32','PZN','ITF','ITF14','ISBN','EAN5','EAN2','Code39Ext','DataBar','DataBarStk','DataBarLtd','DataBarExp','DataBarExpStk','Telepen','TelepenNumeric','DXFilmEdge','PDF417','CompactPDF417','MicroPDF417','Aztec','AztecRune','MicroQRCode','RMQRCode','DataMatrix','MaxiCode')

def save_new(path,raw):
 with Path(path).open('xb') as f:f.write(raw)

def batch_make(lines,opts,parent,cancel):
 if not 1<=len(lines)<=100 or any(not s.strip() for s in lines):raise ValueError('一括作成は空行を含まない1～100行です。')
 parent=Path(parent)
 if not parent.is_dir():raise ValueError('保存先の親フォルダーを選んでください。')
 stamp=time.strftime('%Y%m%d-%H%M%S')+'-'+secrets.token_hex(3);stage=parent/('作成中-'+stamp);stage.mkdir();count=0;deadline=time.monotonic()+300
 try:
  for i,text in enumerate(lines,1):
   if time.monotonic()>deadline:raise TimeoutError('一括処理は5分までです。')
   r=jobs.run({'mode':'qr','text':text,'opts':opts},cancel,timeout=min(30,max(.01,deadline-time.monotonic())))
   if cancel.is_set():raise InterruptedError('停止しました。')
   save_new(stage/(f'{i:03}.png'),base64.b64decode(r['png'],validate=True))
   if r.get('svg'):save_new(stage/(f'{i:03}.svg'),r['svg'].encode('utf8'))
   count+=1
  if cancel.is_set():raise InterruptedError('停止しました。')
  final=parent/('QRまとめ-'+stamp);stage.rename(final);return {'folder':str(final),'count':count}
 except Exception as e:raise RuntimeError(f'{count}件作成しました。\n{e}\n途中の保存先：{stage}') from e

class App:
 def __init__(self,root):
  self.root=root;root.title('きういQR');root.geometry('1120x840');root.minsize(1000,760);self.busy=False;self.closing=False;self.cancel=threading.Event();self.events=queue.Queue();self.result=None;self.rows=[];self.images={};self.paths=[];self.options={'qr':{},'barcode':{},'decode':{}};self.folder=None;self.revision=0
  self.status=tk.StringVar(value='内容を入力して「作成して確認」を押してください。');self.kind=tk.StringVar(value='QRコード');self.ecc=tk.StringVar(value='M');self.style=tk.StringVar(value='四角');self.gradient=tk.StringVar(value='単色');self.box=tk.StringVar(value='8');self.foreground=tk.StringVar(value='#000000');self.background=tk.StringVar(value='#ffffff');self.color2=tk.StringVar(value='#163b70');self.logo=tk.StringVar()
  style=ttk.Style();style.theme_use('clam');style.configure('.',font=('Yu Gothic UI',10));style.configure('Title.TLabel',font=('Yu Gothic UI',21,'bold'))
  out=ttk.Frame(root,padding=16);out.pack(fill='both',expand=True);ttk.Label(out,text='きういQR',style='Title.TLabel').pack(anchor='w');ttk.Label(out,text='URLやメモをQRに。画像のQR・バーコードも、PC内だけで読み取れます。').pack(anchor='w',pady=(0,10))
  self.book=ttk.Notebook(out);self.book.pack(fill='both',expand=True)
  make=ttk.Frame(self.book,padding=12);read=ttk.Frame(self.book,padding=12);batch=ttk.Frame(self.book,padding=12)
  for frame,name in [(make,'QR・バーコードを作る'),(read,'画像から読み取る'),(batch,'QRをまとめて作る')]:self.book.add(frame,text=name)
  left=ttk.Frame(make);left.pack(side='left',fill='both',expand=True);right=ttk.Frame(make,width=350);right.pack(side='right',fill='y',padx=(16,0));right.pack_propagate(False)
  ttk.Label(left,text='QRにするURL・文章 / バーコードの内容').pack(anchor='w');self.text=tk.Text(left,height=9,wrap='word',font=('Yu Gothic UI',11));self.text.pack(fill='both',expand=True,pady=5);self.text.insert('1.0','https://kiwi-garakuta.pages.dev/')
  tools=ttk.Frame(left);tools.pack(fill='x',pady=5)
  for label,kind in [('Wi-Fi','wifi'),('連絡先','contact'),('メール','mail')]:self.button(tools,label+'を入力',lambda k=kind:self.template(k)).pack(side='left',padx=(0,5))
  fields=ttk.Frame(left);fields.pack(fill='x',pady=5);fields.columnconfigure(1,weight=1)
  for row,(label,var,values) in enumerate([('種類',self.kind,KINDS),('誤り訂正（QR）',self.ecc,('L','M','Q','H')),('形（QR）',self.style,tuple(STYLES)),('色の塗り方（QR）',self.gradient,tuple(GRADIENTS)),('1マスの大きさ',self.box,('2','4','6','8','10','12','16'))]):
   ttk.Label(fields,text=label).grid(row=row,column=0,sticky='w',pady=3);ttk.Combobox(fields,textvariable=var,values=values,state='readonly').grid(row=row,column=1,sticky='ew',padx=5)
  colors=ttk.Frame(left);colors.pack(fill='x',pady=5)
  for label,var in [('線の色',self.foreground),('背景',self.background),('2色目',self.color2)]:
   self.button(colors,label,lambda v=var:self.color(v)).pack(side='left');ttk.Entry(colors,textvariable=var,width=9).pack(side='left',padx=(2,6))
  f=ttk.Frame(left);f.pack(fill='x',pady=6);self.button(f,'中央の画像を選ぶ',self.choose_logo).pack(side='left');ttk.Entry(f,textvariable=self.logo).pack(side='left',fill='x',expand=True,padx=5);self.button(f,'外す',lambda:self.logo.set('')).pack(side='left')
  ttk.Label(left,text='中央の画像は誤り訂正Hのときだけ使えます。色・装飾付きQRはPNGで保存します。',wraplength=620).pack(anchor='w',pady=4)
  f=ttk.Frame(left);f.pack(fill='x',pady=6);self.button(f,'作成して確認（F5）',self.make).pack(side='left');self.button(f,'詳細設定',lambda:self.advanced('qr' if self.kind.get()=='QRコード' else 'barcode')).pack(side='left',padx=6)
  self.preview=ttk.Label(right,text='ここにプレビューを表示します',anchor='center');self.preview.pack(fill='both',expand=True);self.info=ttk.Label(right,text='',wraplength=330,justify='center');self.info.pack(pady=8)
  f=ttk.Frame(right);f.pack(pady=10);self.button(f,'PNGを保存',lambda:self.export_image('png')).pack(side='left',padx=3);self.button(f,'SVGを保存',lambda:self.export_image('svg')).pack(side='left',padx=3)
  ttk.Label(right,text='作成後に画像を読み戻して内容を確認します。\n利用するスマートフォンでも読み取ってください。',wraplength=330,justify='center').pack(pady=10)
  f=ttk.Frame(read);f.pack(fill='x')
  for label,cmd in [('画像を追加',self.add_images),('一覧をクリア',self.clear_images),('読み取る',self.read),('詳細設定',lambda:self.advanced('decode'))]:self.button(f,label,cmd).pack(side='left',padx=(0,6))
  self.filelist=tk.Listbox(read,height=3);self.filelist.pack(fill='x',pady=7)
  pane=ttk.Frame(read);pane.pack(fill='both',expand=True);pane.columnconfigure(0,weight=1);pane.columnconfigure(1,weight=1);pane.rowconfigure(0,weight=1)
  columns=('画像','種類','内容');self.table=ttk.Treeview(pane,columns=columns,show='headings',height=6)
  for c,w in zip(columns,(150,100,350)):self.table.heading(c,text=c);self.table.column(c,width=w)
  self.table.grid(row=0,column=0,sticky='nsew');self.table.bind('<<TreeviewSelect>>',self.select_result)
  self.read_preview=ttk.Label(pane,anchor='center');self.read_preview.grid(row=0,column=1,sticky='nsew',padx=10)
  self.details=tk.Text(read,height=7,wrap='word',state='disabled');self.details.pack(fill='x',pady=5)
  f=ttk.Frame(read);f.pack(fill='x')
  for label,cmd in [('内容をコピー',self.copy_text),('内容を作成欄へ',self.to_create),('TXTを保存',lambda:self.export_report('txt')),('JSONを保存',lambda:self.export_report('json'))]:self.button(f,label,cmd).pack(side='left',padx=(0,5))
  ttk.Label(read,text='画像は32件まで。PNG・JPEG・GIF・BMP・WebP・TIFFに対応（最初の1フレーム）。URLは自動では開きません。',wraplength=1000).pack(anchor='w',pady=8)
  ttk.Label(batch,text='1行に1つのURL・文章を入力します（100件まで、空行なし）。QRの色・形・誤り訂正などは作成タブの設定を使います。',wraplength=1000).pack(anchor='w');self.batch_text=tk.Text(batch,height=15,wrap='none',font=('Yu Gothic UI',11));self.batch_text.pack(fill='both',expand=True,pady=8)
  self.button(batch,'保存先を選んでまとめて作成',self.batch).pack(anchor='w',pady=8);ttk.Label(batch,text='新しいフォルダーへ番号付きPNGを保存します。白黒・四角形のQRはSVGも保存します。\n失敗・停止時は作成済みのファイルを「作成中-...」フォルダーに残します。',wraplength=1000).pack(anchor='w')
  self.logbox=tk.Text(out,height=4,wrap='word',state='disabled');self.logbox.pack(fill='x',pady=8)
  f=ttk.Frame(out);f.pack(fill='x');ttk.Label(f,textvariable=self.status,wraplength=850).pack(side='left',fill='x',expand=True);self.button(f,'保存先を開く',self.open_folder).pack(side='right',padx=5);self.stop=ttk.Button(f,text='停止',command=self.cancel.set,state='disabled');self.stop.pack(side='right');self.progress=ttk.Progressbar(out,mode='indeterminate');self.progress.pack(fill='x',pady=(6,0))
  for var in (self.kind,self.ecc,self.style,self.gradient,self.box,self.foreground,self.background,self.color2,self.logo):var.trace_add('write',lambda *a:self.invalidate())
  self.text.bind('<<Modified>>',self.text_changed);self.text.edit_modified(False);root.bind('<F5>',lambda e:self.guard(self.make) if self.book.index(self.book.select())==0 else None);root.protocol('WM_DELETE_WINDOW',self.close);root.after(70,self.poll)

 def button(self,p,text,fn):return ttk.Button(p,text=text,command=lambda:self.guard(fn))
 def guard(self,fn):
  if self.busy:return
  try:fn()
  except Exception as e:messagebox.showerror('確認してください',str(e),parent=self.root)
 def log(self,s):self.logbox.configure(state='normal');self.logbox.delete('1.0','end');self.logbox.insert('1.0',str(s)[:10000]);self.logbox.configure(state='disabled')
 def invalidate(self):
  self.revision+=1;self.result=None;self.info.configure(text='内容や設定を変えたら「作成して確認」を押してください。')
 def text_changed(self,event):
  if self.text.edit_modified():self.invalidate();self.text.edit_modified(False)
 def qr_options(self):
  return {'ecc':self.ecc.get(),'box':int(self.box.get()),'style':STYLES[self.style.get()],'gradient':GRADIENTS[self.gradient.get()],'foreground':self.foreground.get(),'background':self.background.get(),'color2':self.color2.get(),'logo':self.logo.get(),**self.options['qr']}
 def color(self,var):
  c=colorchooser.askcolor(var.get(),parent=self.root)[1]
  if c:var.set(c)
 def choose_logo(self):
  p=filedialog.askopenfilename(parent=self.root,filetypes=[('画像','*.png *.jpg *.jpeg')])
  if p:self.logo.set(p)
 def launch(self,label,fn,done):
  if self.busy:return
  self.busy=True;self.cancel.clear();self.status.set(label+'…');self.progress.start();self.stop.configure(state='normal')
  def work():
   try:self.events.put((True,fn(),done,label))
   except Exception as e:self.events.put((False,str(e),None,label))
  threading.Thread(target=work,daemon=True).start()
 def poll(self):
  try:
   ok,r,done,label=self.events.get_nowait();self.busy=False;self.progress.stop();self.stop.configure(state='disabled')
   if ok:
    self.status.set(label+'：完了')
    try:done(r)
    except Exception as e:self.log(str(e));self.status.set('結果を表示できませんでした。')
   else:
    self.log(r);self.status.set('停止しました。' if self.cancel.is_set() else '処理できませんでした。')
    if not self.cancel.is_set() and not self.closing:messagebox.showerror('処理できませんでした',r,parent=self.root)
  except queue.Empty:pass
  if self.closing and not self.busy:self.root.destroy();return
  self.root.after(70,self.poll)
 def close(self):
  if self.busy:self.closing=True;self.cancel.set();self.status.set('処理の停止を待っています…')
  else:self.root.destroy()
 def show_image(self,widget,raw,key):
  with Image.open(io.BytesIO(base64.b64decode(raw,validate=True))) as im:
   im.load();im.thumbnail((330,340),Image.Resampling.NEAREST);photo=ImageTk.PhotoImage(im.copy())
  self.images[key]=photo;widget.configure(image=photo,text='')
 def make(self):
  self.result=None;kind=self.kind.get();text=self.text.get('1.0','end-1c');opts=self.qr_options() if kind=='QRコード' else dict(self.options['barcode']);task={'mode':'qr' if kind=='QRコード' else 'barcode','text':text,'opts':opts,'format':kind};revision=self.revision
  def done(r):
   if revision!=self.revision:self.result=None;self.log('処理中に内容や設定が変わりました。もう一度作成してください。');return
   self.result=r;self.show_image(self.preview,r['png'],'create');self.info.configure(text=f"{r['size'][0]} × {r['size'][1]} px / 読み戻し確認済み"+(' / SVG対応' if r.get('svg') else ' / PNGのみ'));self.log('内容を読み戻して確認しました。\n'+('バーコード内の内容：'+r['text'] if kind!='QRコード' else 'PNGを保存できます。SVGは白黒・四角形のQRで利用できます。'))
  self.launch('コード作成',lambda:jobs.run(task,self.cancel),done)
 def export_image(self,kind):
  if not self.result:raise ValueError('先に「作成して確認」を押してください。')
  raw=base64.b64decode(self.result['png'],validate=True) if kind=='png' else self.result.get('svg','').encode('utf8')
  if not raw:raise ValueError('この装飾ではPNGで保存してください。SVGは白黒・四角形のQRで使えます。')
  path=filedialog.asksaveasfilename(parent=self.root,defaultextension='.'+kind,filetypes=[(kind.upper(),'*.'+kind)],initialfile='コード.'+kind)
  if path:save_new(path,raw);self.folder=str(Path(path).parent);self.log('保存しました：'+path)
 def add_images(self):
  files=filedialog.askopenfilenames(parent=self.root,filetypes=[('画像','*.png *.jpg *.jpeg *.gif *.bmp *.webp *.tif *.tiff')]);new=list(dict.fromkeys([*self.paths,*files]))
  if len(new)>32:raise ValueError('画像は32件までです。')
  self.paths=new;self.filelist.delete(0,'end')
  for p in new:self.filelist.insert('end',p)
 def clear_images(self):self.paths=[];self.rows=[];self.filelist.delete(0,'end');self.table.delete(*self.table.get_children());self.set_details('')
 def read(self):
  task={'mode':'decode','paths':list(self.paths),'opts':dict(self.options['decode'])}
  def done(r):
   self.rows=r['rows'];self.table.delete(*self.table.get_children())
   for i,row in enumerate(self.rows):self.table.insert('','end',iid=str(i),values=(Path(row['file']).name,row['format'],row['text'][:100].replace('\n',' ')))
   if r.get('png'):self.show_image(self.read_preview,r['png'],'read')
   if self.rows:self.table.selection_set('0');self.select_result()
   self.log('読み取り結果：'+str(sum(1 for r in self.rows if r['valid']))+'件。読み取り内容を選んでコピー・保存できます。')
  self.launch('画像の読み取り',lambda:jobs.run(task,self.cancel),done)
 def row(self):
  selected=self.table.selection()
  if len(selected)!=1:raise ValueError('読み取り結果を1件選んでください。')
  return self.rows[int(selected[0])]
 def set_details(self,s):self.details.configure(state='normal');self.details.delete('1.0','end');self.details.insert('1.0',s[:70000]);self.details.configure(state='disabled')
 def select_result(self,event=None):
  if not self.table.selection():return
  r=self.row();self.set_details(r['text']+('\n\n注意：'+r['error'] if r['error'] else '')+'\n\n種類：'+r['format'])
 def copy_text(self):
  r=self.row();self.root.clipboard_clear();self.root.clipboard_append(r['text']);self.log('選んだ内容をコピーしました。')
 def to_create(self):
  r=self.row()
  if not r['valid']:raise ValueError('正常に読み取れた内容を選んでください。')
  self.text.delete('1.0','end');self.text.insert('1.0',r['text']);self.kind.set('QRコード');self.book.select(0)
 def export_report(self,kind):
  if not self.rows:raise ValueError('先に画像を読み取ってください。')
  raw=json.dumps(self.rows,ensure_ascii=False,indent=2) if kind=='json' else '\n\n'.join(Path(r['file']).name+' / '+r['format']+'\n'+r['text']+('\n'+r['error'] if r['error'] else '') for r in self.rows)
  p=filedialog.asksaveasfilename(parent=self.root,defaultextension='.'+kind,initialfile='読み取り結果.'+kind)
  if p:save_new(p,raw.encode('utf8'));self.folder=str(Path(p).parent);self.log('保存しました：'+p)
 def batch(self):
  lines=self.batch_text.get('1.0','end-1c').splitlines();opts=self.qr_options();parent=filedialog.askdirectory(parent=self.root,title='新しいQRフォルダーを作る場所')
  if not parent:return
  def done(r):self.folder=r['folder'];self.log(str(r['count'])+'件作成しました。\n'+r['folder'])
  self.launch('QRの一括作成',lambda:batch_make(lines,opts,parent,self.cancel),done)
 def template(self,kind):
  fields={'wifi':[('ssid','Wi-Fi名'),('password','パスワード'),('auth','方式：WPA / WEP / nopass'),('hidden','非表示：true / false')],'contact':[('name','名前'),('phone','電話番号'),('email','メール'),('org','組織・会社')],'mail':[('email','宛先メール'),('subject','件名'),('body','本文（1行）')]}[kind]
  win=tk.Toplevel(self.root);win.title({'wifi':'Wi-FiのQR','contact':'連絡先のQR','mail':'メールのQR'}[kind]);win.geometry('550x360');variables={}
  if kind=='wifi':ttk.Label(win,text='作成するQRにはWi-Fiのパスワードが含まれます。').pack(pady=8)
  for key,label in fields:
   f=ttk.Frame(win);f.pack(fill='x',padx=15,pady=5);ttk.Label(f,text=label,width=27).pack(side='left');v=tk.StringVar(value='WPA' if key=='auth' else 'false' if key=='hidden' else '');variables[key]=v;ttk.Entry(f,textvariable=v,show='●' if key=='password' else '').pack(side='left',fill='x',expand=True)
  def apply():
   from engine import template
   result=template(kind,{k:v.get() for k,v in variables.items()});self.text.delete('1.0','end');self.text.insert('1.0',result);self.kind.set('QRコード');win.destroy()
  self.button(win,'作成欄へ入れる',apply).pack(pady=12)
 def advanced(self,mode):
  descriptions={'qr':'version: 0自動/1～40、border:4～16、optimize:0～100、mask:-1自動/0～7、svg_kind:path/rect/fragment。作成タブの項目も同名で上書きできます。','barcode':'scale:1～10、hrt:true/false、ec_level、eci、gs1、reader_init、force_square、columns、rows、version、data_mask。形式ごとの対応条件があります。','decode':'formats:形式名の配列、try_rotate/try_downscale/try_invert/is_pure/return_errors:true/false、text_mode:Plain/ECI/HRI/Escaped/Hex/HexECI、binarizer:LocalAverage/GlobalHistogram/FixedThreshold/BoolCast、ean_add_on_symbol:Ignore/Read/Require。'}
  win=tk.Toplevel(self.root);win.title('詳細設定');win.geometry('800x530');ttk.Label(win,text='JSON形式で指定します。設定は今回の起動中のみです。\n'+descriptions[mode],wraplength=760).pack(padx=12,pady=10,anchor='w');edit=tk.Text(win,height=12);edit.pack(fill='both',expand=True,padx=12);edit.insert('1.0',json.dumps(self.options[mode],ensure_ascii=False,indent=2))
  def apply():
   data=json.loads(edit.get('1.0','end'))
   if not isinstance(data,dict) or len(data)>32:raise ValueError('設定は32項目以内のJSONオブジェクトです。')
   self.options[mode]=data;self.invalidate();win.destroy()
  self.button(win,'適用',apply).pack(pady=10)
 def open_folder(self):
  if self.folder and Path(self.folder).is_dir():os.startfile(self.folder)

if __name__=='__main__':
 multiprocessing.freeze_support()
 App(tk.Tk()).root.mainloop()
