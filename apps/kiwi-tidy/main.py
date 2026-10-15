"""Compare duplicate files and similar photos on this PC."""
import json,os,queue,sys,threading,tkinter as tk
from pathlib import Path
from tkinter import ttk,filedialog,messagebox
if not getattr(sys,'frozen',False):sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'common'))
from runtime import resource_path
from core import MODES,scan,export_report
from options import SCHEMA,validate_options
from PIL import Image,ImageOps,ImageTk

METHODS={'HASH':'内容が同じ','NAME':'名前が同じ','SIZE':'サイズが同じ','SIZE_NAME':'名前とサイズが同じ','TAGS':'曲名などのタグ','CONTENT':'音の内容'}

class App(tk.Tk):
 def __init__(self):
  super().__init__();self.title('きうい重複チェック');self.geometry('1120x800');self.minsize(960,700)
  self.q=queue.Queue();self.cancel=threading.Event();self.worker=None;self.closing=False;self.result=None;self.rows={};self.photos=[];self.controls=[];self.extra={}
  self.mode=tk.StringVar(value=MODES['dup']);self.method=tk.StringVar(value=METHODS['HASH']);self.diff=tk.StringVar(value='5');self.hashsize=tk.StringVar(value='16');self.min_size=tk.StringVar(value='1');self.max_size=tk.StringVar();self.extensions=tk.StringVar();self.threads=tk.StringVar(value='4');self.recursive=tk.BooleanVar(value=True);self.status=tk.StringVar(value='対象フォルダーを選んでください。元のファイルの削除や変更はしません。')
  self.build();self.protocol('WM_DELETE_WINDOW',self.close);self.after(100,self.poll)
 def track(self,w,state='normal'):
  self.controls.append((w,state));return w
 def button(self,parent,text,command):return self.track(ttk.Button(parent,text=text,command=command))
 def build(self):
  style=ttk.Style(self);style.configure('TButton',padding=4);style.configure('Title.TLabel',font=('Yu Gothic UI',17,'bold'));style.configure('Treeview',rowheight=25)
  frame=ttk.Frame(self,padding=12);frame.pack(fill='both',expand=True)
  top=ttk.Frame(frame);top.pack(fill='x');ttk.Label(top,text='きうい重複チェック',style='Title.TLabel').pack(side='left');ttk.Label(top,text='同じファイル・似た写真をまとめて確認').pack(side='left',padx=18)
  self.button(top,'使い方',self.help).pack(side='right')
  dirs=ttk.Frame(frame);dirs.pack(fill='x',pady=8);self.path_boxes={}
  for i,(key,title) in enumerate([('directories','対象フォルダー'),('excluded','除外するフォルダー'),('references','比較の基準フォルダー')]):
   col=ttk.LabelFrame(dirs,text=title,padding=5);col.grid(row=0,column=i,sticky='nsew',padx=3);dirs.columnconfigure(i,weight=1)
   t=self.track(tk.Text(col,height=3,width=32,wrap='none'));t.pack(fill='x');self.path_boxes[key]=t
   bar=ttk.Frame(col);bar.pack(fill='x');self.button(bar,'追加',lambda k=key:self.add_folder(k)).pack(side='left');self.button(bar,'クリア',lambda k=key:self.path_boxes[k].delete('1.0','end')).pack(side='left')
  bar=ttk.Frame(frame);bar.pack(fill='x');ttk.Label(bar,text='検査').pack(side='left');combo=self.track(ttk.Combobox(bar,textvariable=self.mode,values=list(MODES.values()),width=24,state='readonly'),'readonly');combo.pack(side='left',padx=5);combo.bind('<<ComboboxSelected>>',self.mode_changed)
  ttk.Label(bar,text='比較方法').pack(side='left');self.method_box=self.track(ttk.Combobox(bar,textvariable=self.method,values=[METHODS[k] for k in ('HASH','NAME','SIZE','SIZE_NAME')],width=19,state='readonly'),'readonly');self.method_box.pack(side='left',padx=4)
  ttk.Label(bar,text='写真の許容差').pack(side='left');self.diff_box=self.track(ttk.Entry(bar,textvariable=self.diff,width=4));self.diff_box.pack(side='left',padx=4);self.diff_box.configure(state='disabled')
  settings=ttk.Frame(frame);settings.pack(fill='x',pady=6)
  for label,var,width in [('最小B',self.min_size,9),('最大B（空欄で上限なし）',self.max_size,10),('拡張子',self.extensions,12),('CPUスレッド',self.threads,4)]:
   ttk.Label(settings,text=label).pack(side='left');w=self.track(ttk.Entry(settings,textvariable=var,width=width));w.pack(side='left',padx=4)
   if var is self.min_size:self.min_box=w
   if var is self.max_size:self.max_box=w
  self.track(ttk.Checkbutton(settings,text='サブフォルダーも調べる',variable=self.recursive)).pack(side='left',padx=5);self.button(settings,'詳細設定',self.advanced).pack(side='right')
  bar=ttk.Frame(frame);bar.pack(fill='x',pady=(0,6));self.start_button=self.button(bar,'検索する',self.start);self.start_button.pack(side='left');self.stop_button=ttk.Button(bar,text='停止',command=self.cancel.set,state='disabled');self.stop_button.pack(side='left',padx=6)
  self.button(bar,'選択した場所を表示',self.reveal).pack(side='left');self.button(bar,'パスをコピー',self.copy_paths).pack(side='left',padx=5);self.button(bar,'選択の詳細',self.item_details).pack(side='left');self.button(bar,'レポート保存',self.save).pack(side='right');self.button(bar,'検索ログ',self.show_log).pack(side='right',padx=5)
  tree_frame=ttk.Frame(frame);tree_frame.pack(fill='both',expand=True)
  self.tree=ttk.Treeview(tree_frame,columns=('size','dims','diff','ref','path'),selectmode='extended');self.tree.heading('#0',text='グループ / ファイル名');self.tree.column('#0',width=210,minwidth=100)
  for key,title,width in [('size','サイズ(B)',90),('dims','画像サイズ',95),('diff','差',45),('ref','基準',45),('path','場所',500)]:self.tree.heading(key,text=title);self.tree.column(key,width=width,minwidth=40,stretch=key=='path')
  self.tree.grid(row=0,column=0,sticky='nsew');scroll=ttk.Scrollbar(tree_frame,orient='vertical',command=self.tree.yview);scroll.grid(row=0,column=1,sticky='ns');sx=ttk.Scrollbar(tree_frame,orient='horizontal',command=self.tree.xview);sx.grid(row=1,column=0,sticky='ew');self.tree.configure(yscrollcommand=scroll.set,xscrollcommand=sx.set);tree_frame.rowconfigure(0,weight=1);tree_frame.columnconfigure(0,weight=1);self.tree.bind('<<TreeviewSelect>>',self.preview)
  preview=ttk.Frame(frame);preview.pack(fill='x',pady=5);self.preview_labels=[ttk.Label(preview,text='写真を選ぶと表示します（2枚まで）',anchor='center') for _ in range(2)]
  for w in self.preview_labels:w.pack(side='left',fill='x',expand=True)
  ttk.Label(frame,textvariable=self.status,wraplength=1050).pack(fill='x',pady=4)
 def mode_key(self):return next(k for k,v in MODES.items() if v==self.mode.get())
 def mode_changed(self,event=None):
  mode=self.mode_key();values=['TAGS','CONTENT'] if mode=='music' else ['HASH','NAME','SIZE','SIZE_NAME'];self.method_box.configure(values=[METHODS[k] for k in values]);self.method.set(METHODS[values[0]]);self.extra={};self.refresh_mode_controls()
  if mode not in ('dup','image','music'):self.path_boxes['references'].delete('1.0','end')
  self.status.set('似た写真・名前やサイズだけの一致は、内容が同じという意味ではありません。')
 def refresh_mode_controls(self):
  self.method_box.configure(state='readonly' if self.mode_key() in ('dup','music') else 'disabled');self.diff_box.configure(state='normal' if self.mode_key()=='image' else 'disabled')
  self.min_box.configure(state='normal' if 'minimal-file-size' in SCHEMA[self.mode_key()] else 'disabled');self.max_box.configure(state='normal' if 'maximal-file-size' in SCHEMA[self.mode_key()] else 'disabled')
 def add_folder(self,key):
  p=filedialog.askdirectory(parent=self)
  if p:self.path_boxes[key].insert('end',p+'\n')
 def configuration(self):
  mode=self.mode_key();o=dict(self.extra)
  if mode=='bad-names' and not any(k in o for k in ('uppercase-extension','emoji-used','space-at-start-or-end','non-ascii-graphical','restricted-charset','remove-duplicated-non-alphanumeric')):o.update({'uppercase-extension':True,'space-at-start-or-end':True,'remove-duplicated-non-alphanumeric':True})
  o['thread-number']=int(self.threads.get());o['not-recursive']=not self.recursive.get()
  if 'minimal-file-size' in SCHEMA[mode]:o['minimal-file-size']=int(self.min_size.get())
  if self.max_size.get() and 'maximal-file-size' in SCHEMA[mode]:o['maximal-file-size']=int(self.max_size.get())
  if self.extensions.get().strip():o['allowed-extensions']=self.extensions.get().strip()
  if mode in ('dup','music'):o['search-method']=next(k for k,v in METHODS.items() if v==self.method.get())
  if mode=='image':o.update({'max-difference':int(self.diff.get())})
  return mode,validate_options(mode,o)
 def start(self):
  if self.worker and self.worker.is_alive():return
  try:
   mode,opts=self.configuration();paths={k:[s.strip() for s in t.get('1.0','end').splitlines() if s.strip()] for k,t in self.path_boxes.items()}
  except Exception as e:messagebox.showerror('設定を確認してください',str(e),parent=self);return
  self.cancel.clear();self.busy(True);self.status.set('検索中です。元のファイルは変更しません。')
  def job():
   try:self.q.put(('result',scan(mode,paths['directories'],paths['excluded'],paths['references'],opts,self.cancel)))
   except Exception as e:self.q.put(('error',str(e)))
  self.worker=threading.Thread(target=job,daemon=True);self.worker.start()
 def busy(self,value):
  for w,state in self.controls:w.configure(state='disabled' if value else state)
  self.stop_button.configure(state='normal' if value else 'disabled')
  if not value:self.refresh_mode_controls()
 def poll(self):
  try:
   while True:
    kind,value=self.q.get_nowait();self.busy(False)
    if kind=='result':self.result=value;self.display(value)
    else:
     self.status.set(value+(' 前の検索結果を表示しています。' if self.result else ''))
     if not self.closing and not self.cancel.is_set():messagebox.showerror('検索を完了できませんでした',value,parent=self)
  except queue.Empty:pass
  if self.closing and (not self.worker or not self.worker.is_alive()):self.destroy();return
  self.after(100,self.poll)
 def display(self,result):
  for child in self.tree.get_children():self.tree.delete(child)
  self.rows={};count=0
  for i,group in enumerate(result['groups'],1):
   parent=self.tree.insert('','end',text=f'{i} / {len(group)}件',open=True)
   for row in group:
    dims=f"{row['width']}×{row['height']}" if 'width' in row and 'height' in row else ''
    iid=self.tree.insert(parent,'end',text=Path(row['path']).name,values=(row.get('size',''),dims,row.get('difference',''),'基準' if row.get('reference') else '',row['path']));self.rows[iid]=row;count+=1
  self.status.set(f'{MODES[result["mode"]]}：{len(result["groups"])}グループ・{count}件。検索ログも確認してください。');self.preview()
 def selected(self):return [self.rows[k] for k in self.tree.selection() if k in self.rows]
 def preview(self,event=None):
  self.photos=[];rows=self.selected()[:2]
  for i,label in enumerate(self.preview_labels):
   label.configure(image='',text='')
   if i>=len(rows):continue
   p=Path(rows[i]['path'])
   try:
    if p.suffix.lower() not in ('.png','.jpg','.jpeg','.gif','.bmp','.webp') or p.stat().st_size>25*1024*1024:raise ValueError()
    with Image.open(p) as im:
     if im.format not in ('PNG','JPEG','GIF','BMP','WEBP') or im.width*im.height>20_000_000:raise ValueError()
     im=ImageOps.exif_transpose(im);im.thumbnail((250,110));photo=ImageTk.PhotoImage(im.convert('RGB'));self.photos.append(photo);label.configure(image=photo,text='')
   except Exception:label.configure(text=p.name+'（画像表示なし）')
 def reveal(self):
  rows=self.selected()
  if rows and os.name=='nt':
   import subprocess
   p=Path(rows[0]['path'])
   if p.exists():subprocess.Popen(['explorer.exe','/select,',str(p)],creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
 def copy_paths(self):
  rows=self.selected()
  if rows:self.clipboard_clear();self.clipboard_append('\n'.join(r['path'] for r in rows))
 def save(self):
  if not self.result:return
  p=filedialog.asksaveasfilename(parent=self,defaultextension='.csv',filetypes=[('CSV','*.csv'),('JSON','*.json'),('TXT','*.txt')])
  if p:
   try:export_report(self.result,p,Path(p).suffix.lower().lstrip('.'));self.status.set('レポートを保存しました。')
   except Exception as e:messagebox.showerror('保存できませんでした',str(e),parent=self)
 def text_window(self,title,text):
  w=tk.Toplevel(self);w.title(title);w.geometry('850x580');t=tk.Text(w,wrap='word');t.pack(fill='both',expand=True);t.insert('1.0',text);t.configure(state='disabled')
 def item_details(self):
  rows=self.selected()
  if not rows:return
  labels={'path':'場所','size':'サイズ（バイト）','errors':'検査内容','error':'エラー','exif_tags':'撮影情報の項目','current_extension':'現在の拡張子','proper_extensions':'候補の拡張子','reference':'比較の基準','modified_date':'更新時刻（Unix秒）','hash':'内容のハッシュ','width':'幅','height':'高さ','difference':'画像の差'}
  text='\n\n'.join('\n'.join(labels.get(k,k)+'：'+(json.dumps(v,ensure_ascii=False,indent=2) if isinstance(v,(list,dict)) else str(v)) for k,v in row.items()) for row in rows[:20]);self.text_window('選択したファイルの詳細',text)
 def show_log(self):
  if self.result:self.text_window('検索ログ',self.result['notes'])
 def help(self):self.text_window('使い方','1. 対象フォルダーを追加します。必要なら除外・基準フォルダーも指定します。各欄は1行1フォルダーです。\n2. 検査を選び「検索する」を押します。\n3. 結果を選ぶと、写真を2枚まで確認できます。Ctrlキーで複数選択できます。\n4. レポートをTXT・JSON・CSVへ保存できます。\n\nHASHは内容のハッシュで比較します。NAME/SIZE/SIZE_NAMEや似た写真の結果は同一内容を保証しません。基準フォルダー内のファイル同士だけの一致は表示されません。\n\n元のファイルを変更・削除する機能はありません。動画の比較・最適化、動画の破損検査、HEIF/AVIFには対応していません。撮影情報は検出だけ行います。写真の比較結果や破損判定には誤りがありえます。ログの警告も確認してください。\n\n検査は30分、結果ファイルは各16 MiB、表示は50,000件までです。画像のプレビューはPNG/JPEG/GIF/BMP/WebP、25 MiB・2,000万画素までです。\n\n問い合わせ： https://x.com/kiwi_dori')
 def advanced(self):
  mode=self.mode_key();w=tk.Toplevel(self);w.title('詳細設定：'+MODES[mode]);w.geometry('780x560');w.transient(self);w.grab_set()
  ttk.Label(w,text='この検査の追加設定をJSONで指定します。上の画面にある設定は画面の値が優先です。',wraplength=750).pack(pady=5)
  t=tk.Text(w,height=9);t.pack(fill='x');t.insert('1.0',json.dumps(self.extra,ensure_ascii=False,indent=2));schema=tk.Text(w,height=13,wrap='word');schema.pack(fill='both',expand=True);schema.insert('1.0','使用できる設定（同梱CLIのヘルプに意味を記載）\n'+json.dumps(SCHEMA[mode],ensure_ascii=False,indent=2));schema.configure(state='disabled')
  def apply():
   try:self.extra=validate_options(mode,json.loads(t.get('1.0','end')));w.destroy()
   except Exception as e:messagebox.showerror('設定を確認してください',str(e),parent=w)
  bar=ttk.Frame(w);bar.pack(fill='x');ttk.Button(bar,text='適用',command=apply).pack(side='right');ttk.Button(bar,text='CLIヘルプ',command=lambda:self.text_window('同梱CLIのヘルプ',Path(resource_path('upstream-help.txt',Path(__file__).resolve().parent)).read_text(encoding='utf8'))).pack(side='left')
 def close(self):
  self.closing=True;self.cancel.set()
  if not self.worker or not self.worker.is_alive():self.destroy()
  else:self.status.set('検索を停止して終了します。')
if __name__=='__main__':App().mainloop()
