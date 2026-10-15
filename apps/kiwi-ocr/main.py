"""Local image text recognition, review and explicit exports."""
import base64,csv,io,json,multiprocessing,os,queue,sys,threading,time,tkinter as tk
from pathlib import Path
from tkinter import ttk,filedialog,messagebox
from PIL import Image,ImageTk
import jobs
MODES={'文字を読む':'full','文字の位置だけ':'detect','1行の文字を読む':'line','行の上下を調べる':'angle'}

def save_new(path,raw):
 with Path(path).open('xb') as f:f.write(raw)

class App:
 def __init__(self,root):
  self.root=root;root.title('きうい画像OCR');root.geometry('1250x850');root.minsize(1100,760);self.busy=False;self.closing=False;self.cancel=threading.Event();self.events=queue.Queue();self.states={};self.paths=[];self.displayed=None;self.options={};self.current_rows=[];self.drag=None;self.photo=None;self.mapping=None;self.folder=None
  self.mode=tk.StringVar(value='文字を読む');self.score=tk.StringVar(value='0.5');self.cls=tk.BooleanVar(value=True);self.word=tk.BooleanVar();self.char=tk.BooleanVar();self.view=tk.StringVar(value='行');self.status=tk.StringVar(value='画像を追加してください。');self.info=tk.StringVar(value='')
  s=ttk.Style();s.theme_use('clam');s.configure('.',font=('Yu Gothic UI',10));s.configure('Title.TLabel',font=('Yu Gothic UI',21,'bold'))
  out=ttk.Frame(root,padding=14);out.pack(fill='both',expand=True);ttk.Label(out,text='きうい画像OCR',style='Title.TLabel').pack(anchor='w');ttk.Label(out,text='写真・スクリーンショットの文字を、コピーできる文章に。日本語対応モデルでPC内だけで処理します。').pack(anchor='w',pady=(0,8))
  f=ttk.Frame(out);f.pack(fill='x')
  for label,cmd in [('画像を追加（F4）',self.add),('フォルダーから追加',self.add_folder),('一覧をクリア',self.clear),('選んだ画像を読む（F5）',lambda:self.read(False)),('すべて読む',lambda:self.read(True)),('詳細設定',self.advanced)]:self.button(f,label,cmd).pack(side='left',padx=(0,5))
  f=ttk.Frame(out);f.pack(fill='x',pady=7);ttk.Label(f,text='操作').pack(side='left');ttk.Combobox(f,textvariable=self.mode,values=list(MODES),state='readonly',width=19).pack(side='left',padx=5);ttk.Label(f,text='文字の採用下限').pack(side='left');ttk.Entry(f,textvariable=self.score,width=5).pack(side='left',padx=5)
  for text,var in [('上下の向きを補正',self.cls),('単語の位置',self.word),('文字ごとの位置',self.char)]:ttk.Checkbutton(f,text=text,variable=var).pack(side='left',padx=6)
  content=ttk.Frame(out,height=440);content.grid_propagate(False);content.pack(fill='both',expand=True);content.columnconfigure(1,weight=3);content.columnconfigure(2,weight=2);content.rowconfigure(0,weight=1)
  left=ttk.Frame(content,width=160);left.grid(row=0,column=0,sticky='ns',padx=(0,8));ttk.Label(left,text='画像（20件まで）').pack(anchor='w');self.files=tk.Listbox(left,width=20,height=20,exportselection=False);self.files.pack(fill='both',expand=True,pady=5);self.files.bind('<<ListboxSelect>>',self.selected)
  center=ttk.Frame(content);center.grid(row=0,column=1,sticky='nsew',padx=(0,10));ttk.Label(center,text='画像上をドラッグして、読む範囲を選べます。').pack(anchor='w');self.canvas=tk.Canvas(center,width=520,background='#edf1ed',highlightthickness=0);self.canvas.pack(fill='both',expand=True,pady=5);self.canvas.bind('<Configure>',lambda e:self.draw());self.canvas.bind('<ButtonPress-1>',self.drag_start);self.canvas.bind('<B1-Motion>',self.drag_move);self.canvas.bind('<ButtonRelease-1>',self.drag_end)
  f=ttk.Frame(center);f.pack(fill='x');self.button(f,'右へ90度回転',self.rotate).pack(side='left');self.button(f,'範囲を解除',self.reset_region).pack(side='left',padx=5);self.button(f,'位置付きPNG保存',self.export_image).pack(side='left');ttk.Label(center,textvariable=self.info,wraplength=550).pack(anchor='w',pady=6)
  right=ttk.Frame(content);right.grid(row=0,column=2,sticky='nsew');ttk.Label(right,text='文章（修正してコピー・TXT保存できます）').pack(anchor='w');self.editor=tk.Text(right,width=42,height=10,wrap='word',font=('Yu Gothic UI',12));self.editor.pack(fill='both',expand=True,pady=5)
  f=ttk.Frame(right);f.pack(fill='x')
  for label,cmd in [('全文をコピー',self.copy),('修正文TXT保存',lambda:self.export('txt'))]:self.button(f,label,cmd).pack(side='left',padx=(0,5))
  f=ttk.Frame(right);f.pack(fill='x',pady=7);ttk.Label(f,text='位置の一覧').pack(side='left');cb=ttk.Combobox(f,textvariable=self.view,values=['行','単語・文字'],state='readonly',width=12);cb.pack(side='left',padx=5);cb.bind('<<ComboboxSelected>>',lambda e:self.show_rows())
  self.table=ttk.Treeview(right,columns=('内容','目安'),show='headings',height=6);self.table.heading('内容',text='認識した内容');self.table.heading('目安',text='目安');self.table.column('内容',width=240);self.table.column('目安',width=60,stretch=False);self.table.pack(fill='both',expand=True);self.table.bind('<<TreeviewSelect>>',lambda e:self.draw())
  f=ttk.Frame(right);f.pack(fill='x',pady=7)
  for label,ext in [('CSV保存','csv'),('JSON保存','json'),('Markdown保存','md')]:self.button(f,label,lambda k=ext:self.export(k)).pack(side='left',padx=(0,4))
  ttk.Label(right,text='単語・文字の位置は「文字を読む」で取得できます。位置と目安は認識時の結果です。文章の修正はTXT・コピーへ反映されます。',wraplength=430).pack(anchor='w')
  self.logbox=tk.Text(out,height=3,wrap='word',state='disabled');self.logbox.pack(fill='x',pady=7);f=ttk.Frame(out);f.pack(fill='x');ttk.Label(f,textvariable=self.status,wraplength=1000).pack(side='left',fill='x',expand=True);self.button(f,'保存先を開く',self.open_folder).pack(side='right',padx=5);self.stop=ttk.Button(f,text='停止',command=self.cancel.set,state='disabled');self.stop.pack(side='right');self.progress=ttk.Progressbar(out,mode='indeterminate');self.progress.pack(fill='x',pady=(5,0))
  root.bind('<F4>',lambda e:self.guard(self.add));root.bind('<F5>',lambda e:self.guard(lambda:self.read(False)));root.protocol('WM_DELETE_WINDOW',self.close);root.after(70,self.poll)
 def button(self,p,text,fn):return ttk.Button(p,text=text,command=lambda:self.guard(fn))
 def guard(self,fn):
  if self.busy:return
  try:fn()
  except Exception as e:messagebox.showerror('確認してください',str(e),parent=self.root)
 def log(self,s):self.logbox.configure(state='normal');self.logbox.delete('1.0','end');self.logbox.insert('1.0',str(s)[:12000]);self.logbox.configure(state='disabled')
 def active(self):
  sel=self.files.curselection()
  if not sel:raise ValueError('画像を1件選んでください。')
  return self.paths[sel[0]]
 def add_paths(self,paths):
  paths=list(dict.fromkeys([*self.paths,*[str(Path(p).resolve()) for p in paths]]))
  if len(paths)>20:raise ValueError('画像は20件までです。')
  for p in paths:
   if p not in self.states:self.states[p]={'rotation':0,'region':None,'meta':None,'result':None,'edited':''}
  self.paths=paths;self.files.delete(0,'end')
  for p in paths:self.files.insert('end',Path(p).name)
  if paths:self.files.selection_set(0);self.selected()
 def add(self):self.add_paths(filedialog.askopenfilenames(parent=self.root,title='画像を追加',filetypes=[('画像','*.png *.jpg *.jpeg *.webp *.bmp *.gif *.tif *.tiff')]))
 def add_folder(self):
  path=filedialog.askdirectory(parent=self.root)
  if path:self.add_paths(sorted(p for p in Path(path).iterdir() if p.is_file() and p.suffix.lower() in ('.png','.jpg','.jpeg','.webp','.bmp','.gif','.tif','.tiff')))
 def store_edit(self):
  if self.displayed in self.states and self.states[self.displayed]['result'] is not None:self.states[self.displayed]['edited']=self.editor.get('1.0','end-1c')
 def clear(self):self.paths=[];self.states={};self.files.delete(0,'end');self.displayed=None;self.editor.delete('1.0','end');self.table.delete(*self.table.get_children());self.canvas.delete('all');self.info.set('')
 def selected(self,event=None):
  if not self.files.curselection():return
  self.store_edit();p=self.active();self.displayed=p;self.show()
  if not self.busy and self.states[p]['meta'] is None:self.preview(p)
 def task(self,p,op):return {'op':op,'path':p,'rotation':self.states[p]['rotation'],'region':self.states[p]['region']}
 def launch(self,label,fn,done):
  self.busy=True;self.cancel.clear();self.status.set(label+'…');self.stop.configure(state='normal');self.progress.start()
  def work():
   try:self.events.put(('done',fn(),done,label))
   except Exception as e:self.events.put(('error',jobs.describe(e),None,label))
  threading.Thread(target=work,daemon=True).start()
 def poll(self):
  try:
   event,r,done,label=self.events.get_nowait()
   if event=='item':
    p,result=r;st=self.states[p];st['result']=result;st['meta']=result;st['edited']='\n'.join(x['text'] for x in result['rows']);self.status.set('読み取り済み：'+Path(p).name)
    if self.displayed==p:self.show()
   elif event=='item_error':
    p,error=r;self.states[p]['result']=None;self.states[p]['edited']='';self.log(Path(p).name+'：'+error)
    if self.displayed==p:self.show()
   else:
    self.busy=False;self.progress.stop();self.stop.configure(state='disabled')
    if event=='done':
     self.status.set(label+'：終了')
     try:done(r)
     except Exception as e:self.log(str(e));self.status.set('結果を表示できませんでした。')
    else:
     self.log(r);self.status.set('停止しました。完了した画像の結果は残っています。' if self.cancel.is_set() else '処理できませんでした。')
     if not self.cancel.is_set() and not self.closing:messagebox.showerror('処理できませんでした',r,parent=self.root)
  except queue.Empty:pass
  if self.closing and not self.busy:self.root.destroy();return
  self.root.after(70,self.poll)
 def preview(self,p):
  task=self.task(p,'preview')
  def done(r):self.states[p]['meta']=r;self.show() if self.displayed==p else None
  self.launch('画像の表示',lambda:jobs.run(task,self.cancel),done)
 def show(self):
  if self.displayed not in self.states:return
  s=self.states[self.displayed];self.editor.delete('1.0','end');self.editor.insert('1.0',s['edited']);meta=s['meta']
  if meta:
   with Image.open(io.BytesIO(base64.b64decode(meta['preview'],validate=True))) as im:self.preview_image=im.copy()
   self.info.set(f"処理画像 {meta['size'][0]} × {meta['size'][1]} px / 回転 {s['rotation']}°"+(' / 選択範囲' if s['region'] else ''))
  else:self.preview_image=None;self.info.set('画像を読み込んでいます。')
  self.show_rows()
 def show_rows(self):
  self.current_rows=[];self.table.delete(*self.table.get_children())
  if self.displayed not in self.states:return
  r=self.states[self.displayed]['result']
  if r:
   self.current_rows=r['rows'] if self.view.get()=='行' else [w for row in r['rows'] for w in row['words']]
   for i,row in enumerate(self.current_rows):self.table.insert('','end',iid=str(i),values=(row['text'][:160],f"{row['score']:.0%}"))
  self.draw()
 def draw(self):
  self.canvas.delete('all');self.mapping=None
  im=getattr(self,'preview_image',None)
  if im is None or self.displayed not in self.states:return
  meta=self.states[self.displayed]['meta']
  if not meta:return
  w,h=meta['size'];cw,ch=max(10,self.canvas.winfo_width()),max(10,self.canvas.winfo_height());scale=min(cw/w,ch/h);tw,th=max(1,int(w*scale)),max(1,int(h*scale));x,y=(cw-tw)/2,(ch-th)/2;self.photo=ImageTk.PhotoImage(im.resize((tw,th),Image.Resampling.LANCZOS));self.canvas.create_image(x,y,anchor='nw',image=self.photo);self.mapping=(scale,x,y,w,h)
  selected=self.table.selection();chosen=int(selected[0]) if selected else -1
  for i,row in enumerate(self.current_rows):
   points=[v for px,py in row['box'] for v in (x+px*scale,y+py*scale)];self.canvas.create_polygon(points,outline='#d05230' if i==chosen else '#17825e',fill='',width=3 if i==chosen else 1)
 def drag_start(self,e):
  if not self.busy and self.mapping:self.drag=(e.x,e.y)
 def drag_move(self,e):
  if self.drag and not self.busy:self.canvas.delete('crop');self.canvas.create_rectangle(*self.drag,e.x,e.y,outline='#3571b3',width=2,tags='crop')
 def drag_end(self,e):
  if self.busy or not self.drag or not self.mapping:return
  x0,y0=self.drag;self.drag=None
  if abs(e.x-x0)<5 or abs(e.y-y0)<5:self.canvas.delete('crop');return
  scale,x,y,w,h=self.mapping;box=[int(max(0,min(w,(min(x0,e.x)-x)/scale))),int(max(0,min(h,(min(y0,e.y)-y)/scale))),int(max(0,min(w,(max(x0,e.x)-x)/scale))),int(max(0,min(h,(max(y0,e.y)-y)/scale)))];p=self.active();previous=self.states[p]['region'] or [0,0,w,h]
  box=[box[0]+previous[0],box[1]+previous[1],box[2]+previous[0],box[3]+previous[1]]
  if min(box[2]-box[0],box[3]-box[1])<5:return
  self.states[p].update(region=box,result=None,edited='',meta=None);self.preview(p)
 def rotate(self):
  p=self.active();self.states[p].update(rotation=(self.states[p]['rotation']+90)%360,region=None,result=None,edited='',meta=None);self.preview(p)
 def reset_region(self):
  p=self.active();self.states[p].update(region=None,result=None,edited='',meta=None);self.preview(p)
 def read(self,all_images):
  paths=list(self.paths) if all_images else [self.active()]
  if not paths:raise ValueError('画像を追加してください。')
  self.store_edit();opts={**self.options,'text_score':float(self.score.get()),'use_cls':self.cls.get(),'return_word_box':self.word.get() or self.char.get(),'return_single_char_box':self.char.get()};tasks=[{**self.task(p,'ocr'),'mode':MODES[self.mode.get()],'opts':opts} for p in paths]
  def work():
   done=0;errors=[];deadline=time.monotonic()+600
   for task in tasks:
    if self.cancel.is_set():raise InterruptedError('停止しました。')
    if time.monotonic()>deadline:raise TimeoutError('一括処理は10分までです。')
    try:r=jobs.run(task,self.cancel,timeout=min(120,deadline-time.monotonic()))
    except Exception as e:
     if self.cancel.is_set():raise
     errors.append(Path(task['path']).name+'：'+jobs.describe(e));self.events.put(('item_error',(task['path'],jobs.describe(e)),None,''));continue
    done+=1;self.events.put(('item',(task['path'],r),None,''))
   return done,errors
  def finish(r):
   n,errors=r;self.log(f'{n}画像の処理を完了しました。'+('\n'+ '\n'.join(errors) if errors else '\n認識に誤りがある場合は文章を修正してコピー・TXT保存してください。'));self.status.set('一部の画像を処理できませんでした。' if errors else '読み取りが終わりました。')
  self.launch('文字の読み取り',work,finish)
 def result(self):
  self.store_edit();p=self.active();r=self.states[p]['result']
  if r is None:raise ValueError('先にこの画像を読み取ってください。')
  return r,self.states[p]['edited']
 def copy(self):
  r,text=self.result();self.root.clipboard_clear();self.root.clipboard_append(text);self.log('修正後の文章をコピーしました。')
 def export(self,kind):
  r,text=self.result()
  if kind=='txt':raw=text
  elif kind=='json':raw=json.dumps({k:v for k,v in r.items() if k not in ('preview','task')}|{'edited_text':text},ensure_ascii=False,indent=2)
  elif kind=='md':raw=r['markdown']
  else:
   b=io.StringIO(newline='');writer=csv.writer(b);writer.writerow(['text','score','box','words'])
   for row in r['rows']:writer.writerow([row['text'],row['score'],json.dumps(row['box']),json.dumps(row['words'],ensure_ascii=False)])
   raw='\ufeff'+b.getvalue()
  path=filedialog.asksaveasfilename(parent=self.root,defaultextension='.'+kind,initialfile=Path(self.active()).stem+'-文字.'+kind)
  if path:save_new(path,raw.encode('utf8'));self.folder=str(Path(path).parent);self.log('保存しました：'+path)
 def export_image(self):
  r,text=self.result();path=filedialog.asksaveasfilename(parent=self.root,defaultextension='.png',initialfile=Path(self.active()).stem+'-位置.png')
  if not path:return
  task={'op':'annotate',**r['task'],'result':{k:r[k] for k in ('source_sha256','rows')}}
  def done(result):save_new(path,base64.b64decode(result['png'],validate=True));self.folder=str(Path(path).parent);self.log('保存しました：'+path)
  self.launch('位置付き画像の作成',lambda:jobs.run(task,self.cancel),done)
 def advanced(self):
  win=tk.Toplevel(self.root);win.title('詳細設定');win.geometry('820x560');ttk.Label(win,text='JSONで指定します。設定は今回の起動中だけです。\nthreads(1～16)、det_limit_side_len(64～1536)、det_thresh / det_box_thresh / cls_thresh(0～1)、det_unclip_ratio(0.5～3)、det_max_candidates(1～1000)、det_use_dilation(true/false)、det_score_mode(fast/slow)、rec_batch_num(1～16)、use_preprocess_img / use_vertical_padding(true/false)、min_height(1～100)、width_height_ratio(1～30)。',wraplength=780).pack(padx=12,pady=10,anchor='w');edit=tk.Text(win,height=12);edit.pack(fill='both',expand=True,padx=12);edit.insert('1.0',json.dumps(self.options,ensure_ascii=False,indent=2))
  def apply():
   data=json.loads(edit.get('1.0','end'))
   if not isinstance(data,dict) or len(data)>32:raise ValueError('JSONオブジェクトで指定してください。')
   self.options=data;win.destroy();self.status.set('詳細設定を適用しました。もう一度読み取ってください。')
  self.button(win,'適用',apply).pack(pady=10)
 def open_folder(self):
  if self.folder and Path(self.folder).is_dir():os.startfile(self.folder)
 def close(self):
  if self.busy:self.cancel.set();self.closing=True;self.status.set('停止を待っています…')
  else:self.root.destroy()

if __name__=='__main__':
 multiprocessing.freeze_support()
 app=App(tk.Tk())
 app.root.mainloop()
