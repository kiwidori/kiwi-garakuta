"""Create, inspect and unpack local archives."""
import os,queue,threading,time,tkinter as tk
from tkinter import ttk,filedialog,messagebox
from pathlib import Path
import runner
from cli_options import FORMAT_CHOICES,normalize_format

class App(tk.Tk):
 def __init__(self):
  super().__init__();self.title('きうい圧縮箱');self.geometry('1080x850');self.minsize(1000,790)
  self.paths=[];self.archives=[];self.worker=None;self.cancel=threading.Event();self.events=queue.Queue();self.closing=False;self.last_folder=None
  self.format=tk.StringVar(value='zip');self.mode=tk.StringVar(value='auto');self.level=tk.StringVar(value='6');self.threads=tk.StringVar(value='2');self.hidden=tk.BooleanVar();self.gitignore=tk.BooleanVar();self.tree=tk.BooleanVar(value=True);self.override=tk.StringVar();self.password=tk.StringVar();self.parent=tk.StringVar();self.status=tk.StringVar(value='元ファイルを残して、圧縮・展開します。')
  top=ttk.Frame(self,padding=14);top.pack(fill='both',expand=True)
  ttk.Label(top,text='きうい圧縮箱',font=('Yu Gothic UI',21,'bold')).pack(anchor='w')
  ttk.Label(top,text='写真や書類をまとめる・届いた書庫を開く。処理はPC内で行います。').pack(anchor='w',pady=(2,10))
  self.tabs=ttk.Notebook(top);self.tabs.pack(fill='x');self.pack_tab=ttk.Frame(self.tabs,padding=12);self.open_tab=ttk.Frame(self.tabs,padding=12)
  self.tabs.add(self.pack_tab,text='圧縮する');self.tabs.add(self.open_tab,text='中身を確認・展開する')
  f=ttk.Frame(self.pack_tab);f.pack(fill='x')
  ttk.Button(f,text='ファイルを追加',command=self.add_files).pack(side='left');ttk.Button(f,text='フォルダーを追加',command=self.add_folder).pack(side='left',padx=6);ttk.Button(f,text='選んだ項目を外す',command=lambda:self.remove(False)).pack(side='left')
  self.files=self.box(self.pack_tab,5)
  f=ttk.Frame(self.pack_tab);f.pack(fill='x',pady=6)
  ttk.Label(f,text='保存形式').pack(side='left');ttk.Combobox(f,textvariable=self.format,values=FORMAT_CHOICES,width=16).pack(side='left',padx=8)
  ttk.Label(f,text='圧縮方法').pack(side='left');ttk.Combobox(f,textvariable=self.mode,values=['auto','fast','slow','level'],state='readonly',width=8).pack(side='left',padx=8)
  ttk.Label(f,text='指定レベル').pack(side='left');ttk.Spinbox(f,from_=-7,to=22,textvariable=self.level,width=5).pack(side='left',padx=6)
  ttk.Label(self.pack_tab,text='auto：標準 / fast：速度優先 / slow：容量優先 / level：数値指定（有効範囲は形式ごとに異なります）').pack(anchor='w')
  ttk.Button(self.pack_tab,text='保存名を選んで圧縮する',command=self.start_compress).pack(anchor='w',pady=(10,0))
  f=ttk.Frame(self.open_tab);f.pack(fill='x');ttk.Button(f,text='書庫を追加',command=self.add_archives).pack(side='left');ttk.Button(f,text='選んだ書庫を外す',command=lambda:self.remove(True)).pack(side='left',padx=6)
  self.archive_box=self.box(self.open_tab,5)
  f=ttk.Frame(self.open_tab);f.pack(fill='x',pady=5)
  ttk.Label(f,text='書庫パスワード').pack(side='left');self.password_entry=ttk.Entry(f,textvariable=self.password,show='●',width=27);self.password_entry.pack(side='left',padx=6)
  ttk.Checkbutton(f,text='一覧をツリー表示',variable=self.tree).pack(side='left',padx=8)
  ttk.Label(f,text='形式指定（空欄で自動）').pack(side='left');ttk.Entry(f,textvariable=self.override,width=13).pack(side='left',padx=5)
  f=ttk.Frame(self.open_tab);f.pack(fill='x',pady=4);ttk.Button(f,text='展開先の親フォルダー',command=self.choose_parent).pack(side='left');ttk.Entry(f,textvariable=self.parent).pack(side='left',fill='x',expand=True,padx=6)
  f=ttk.Frame(self.open_tab);f.pack(fill='x',pady=(6,0));ttk.Button(f,text='選んだ書庫の中身を見る',command=self.start_list).pack(side='left');ttk.Button(f,text='選んだ書庫を新しいフォルダーへ展開',command=self.start_extract).pack(side='left',padx=8)
  ttk.Label(self.open_tab,text='一覧は展開せずに確認できます。複数選択した書庫は、一覧でまとめて確認できます。展開は1件ずつです。').pack(anchor='w',pady=(5,0))
  opts=ttk.LabelFrame(top,text='共通設定',padding=8);opts.pack(fill='x',pady=10)
  ttk.Label(opts,text='スレッド数').pack(side='left');ttk.Spinbox(opts,from_=1,to=16,textvariable=self.threads,width=4).pack(side='left',padx=6)
  ttk.Checkbutton(opts,text='隠しファイルを除く',variable=self.hidden).pack(side='left',padx=10);ttk.Checkbutton(opts,text='.gitignoreを使う',variable=self.gitignore).pack(side='left',padx=10)
  ttk.Label(top,text='ZIP・7z・tar・gzip・xz・zstdなどに対応。RARは読み取り専用。パスワード付き書庫の作成はできません。').pack(anchor='w')
  ttk.Label(top,text='1回32対象・合計2 GiB・10,000項目、処理5分まで。フォルダー内のリンクは扱いません。展開後のファイルは自動で開きません。').pack(anchor='w',pady=(2,8))
  f=ttk.Frame(top);f.pack(fill='x');ttk.Label(f,textvariable=self.status).pack(side='left');self.stop=ttk.Button(f,text='停止',command=self.cancel.set,state='disabled');self.stop.pack(side='right')
  self.progress=ttk.Progressbar(top,mode='indeterminate');self.progress.pack(fill='x',pady=6)
  self.log=tk.Text(top,height=10,wrap='word',font=('Yu Gothic UI',10));scroll=ttk.Scrollbar(top,command=self.log.yview);self.log.configure(yscrollcommand=scroll.set);self.log.pack(fill='both',expand=True)
  f=ttk.Frame(top);f.pack(fill='x',pady=(8,0));ttk.Button(f,text='結果をコピー',command=self.copy).pack(side='left');ttk.Button(f,text='結果をTXT保存',command=self.save_log).pack(side='left',padx=6);ttk.Button(f,text='保存先フォルダーを開く',command=self.open_output).pack(side='left')
  ttk.Label(f,text='ouchを利用した非公式GUI · 0.1.0').pack(side='right')
  self.protocol('WM_DELETE_WINDOW',self.close);self.after(70,self.poll)

 def box(self,parent,height):
  f=ttk.Frame(parent);f.pack(fill='x',pady=6);b=tk.Listbox(f,height=height,selectmode='extended',exportselection=False,font=('Yu Gothic UI',10));b.pack(side='left',fill='x',expand=True);s=ttk.Scrollbar(f,command=b.yview);s.pack(side='right',fill='y');b.config(yscrollcommand=s.set);return b
 def refresh(self):
  for box,paths in [(self.files,self.paths),(self.archive_box,self.archives)]:
   box.delete(0,'end')
   for p in paths:box.insert('end',Path(p).name+('  [フォルダー]' if Path(p).is_dir() else ''))
 def add(self,values,archives=False):
  target=self.archives if archives else self.paths
  for p in values:
   if p not in target:target.append(p)
  if len(target)>32:del target[32:];messagebox.showinfo('対象数','32件まで追加できます。',parent=self)
  self.refresh()
 def add_files(self):self.add(filedialog.askopenfilenames(parent=self,title='圧縮するファイル'))
 def add_folder(self):
  p=filedialog.askdirectory(parent=self,title='圧縮するフォルダー')
  if p:self.add([p])
 def add_archives(self):self.add(filedialog.askopenfilenames(parent=self,title='中身を確認・展開する書庫'),True)
 def remove(self,archive):
  box,paths=(self.archive_box,self.archives) if archive else (self.files,self.paths)
  for i in reversed(box.curselection()):del paths[i]
  self.refresh()
 def choose_parent(self):
  p=filedialog.askdirectory(parent=self,title='展開先の親フォルダー')
  if p:self.parent.set(p)
 def options(self,compress=False):
  return dict(threads=int(self.threads.get()),hidden=self.hidden.get(),gitignore=self.gitignore.get(),tree=self.tree.get(),format=normalize_format(self.format.get(),True) if compress else self.override.get(),mode=self.mode.get(),level=int(self.level.get()) if self.mode.get()=='level' else 6)
 def start(self,job,label):
  if self.worker is not None:return
  self.cancel.clear();self.log.delete('1.0','end');self.status.set(label);self.progress.start(15);self.stop.config(state='normal');self.last_folder=None
  def run():
   try:
    text,folder=job();self.events.put(('done',text,folder))
   except Exception as e:self.events.put(('error',str(e),None))
  self.worker=threading.Thread(target=run,daemon=False);self.worker.start()
 def start_compress(self):
  try:
   options=self.options(True);paths=list(self.paths)
   if not paths:raise ValueError('圧縮するファイル・フォルダーを追加してください。')
   dest=filedialog.asksaveasfilename(parent=self,title='新しい圧縮ファイルの保存名',initialfile='まとめ.'+options['format'],defaultextension='.'+options['format'])
   if not dest:return
   self.start(lambda:(runner.compress(paths,dest,options,self.cancel),Path(dest).parent),'圧縮しています…')
  except Exception as e:messagebox.showerror('入力の確認',str(e),parent=self)
 def chosen(self,multiple=False):
  indexes=self.archive_box.curselection()
  if not indexes and len(self.archives)==1:indexes=(0,)
  if not indexes or (not multiple and len(indexes)!=1):raise ValueError('書庫を1件選んでください。' if not multiple else '書庫を選んでください。')
  return [self.archives[i] for i in indexes]
 def start_list(self):
  try:
   options=self.options();paths=self.chosen(True);password=self.password.get();self.start(lambda:(runner.listing(paths,options,self.cancel,password),None),'中身を確認しています…')
  except Exception as e:messagebox.showerror('入力の確認',str(e),parent=self)
 def start_extract(self):
  try:
   options=self.options();path=self.chosen()[0];password=self.password.get();parent=self.parent.get()
   if not parent:raise ValueError('展開先の親フォルダーを選んでください。')
   def job():
    folder,text=runner.extract(path,parent,options,self.cancel,password);return text,folder
   self.start(job,'新しいフォルダーへ展開しています…')
  except Exception as e:messagebox.showerror('入力の確認',str(e),parent=self)
 def poll(self):
  try:
   while True:
    kind,text,folder=self.events.get_nowait();self.password.set('');self.progress.stop();self.stop.config(state='disabled');self.last_folder=folder;self.log.insert('end',text);self.status.set('完了しました。' if kind=='done' else ('停止しました。' if self.cancel.is_set() else '処理できませんでした。結果欄を確認してください。'));self.worker.join(timeout=1);self.worker=None
  except queue.Empty:pass
  if self.closing and not(self.worker and self.worker.is_alive()):self.destroy();return
  self.after(70,self.poll)
 def copy(self):
  text=self.log.get('1.0','end-1c')
  if text:self.clipboard_clear();self.clipboard_append(text)
 def save_log(self):
  text=self.log.get('1.0','end-1c')
  if not text:return
  p=filedialog.asksaveasfilename(parent=self,initialfile='圧縮箱の結果.txt',defaultextension='.txt')
  if p:
   try:runner.save_text(p,text)
   except Exception as e:messagebox.showerror('保存できません',str(e),parent=self)
 def open_output(self):
  if self.last_folder and Path(self.last_folder).is_dir():os.startfile(self.last_folder)
 def close(self):
  self.closing=True;self.cancel.set();self.password.set('');self.status.set('処理を停止しています…')

if __name__=='__main__':App().mainloop()
