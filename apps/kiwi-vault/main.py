"""Local file encryption, decryption and age key management."""
import json,os,queue,secrets,string,threading,time,tkinter as tk
from pathlib import Path
from tkinter import ttk,filedialog,messagebox
import runner

def save_new(path,raw):
 with Path(path).open('xb') as f:f.write(raw)

def generate_password():
 alphabet=string.ascii_letters+string.digits+'-_'
 return ''.join(secrets.choice(alphabet) for _ in range(24))

class App:
 def __init__(self,root):
  self.root=root;root.title('きういファイル金庫');root.geometry('1120x870');root.minsize(1020,800);self.busy=False;self.closing=False;self.cancel=threading.Event();self.events=queue.Queue();self.paths=[];self.recipient_files=[];self.identity_files=[];self.derive_ids=[];self.folder=None;self.base=None;self.inspected=None
  self.op=tk.StringVar(value='encrypt');self.auth=tk.StringVar(value='パスワード');self.passphrase=tk.StringVar();self.confirm=tk.StringVar();self.reveal=tk.BooleanVar();self.armor=tk.BooleanVar();self.keypass=tk.StringVar();self.to_identity=tk.BooleanVar();self.keykind=tk.StringVar(value='X25519（互換性重視）');self.protect=tk.BooleanVar(value=True);self.genpass=tk.StringVar();self.genconfirm=tk.StringVar();self.status=tk.StringVar(value='暗号化したいファイルを選んでください。');self.dest=tk.StringVar(value='保存先の親フォルダーを選んでください。');self.rec_label=tk.StringVar(value='宛先ファイル：なし');self.id_label=tk.StringVar(value='秘密鍵：なし');self.derive_label=tk.StringVar(value='秘密鍵：なし');self.info_path=None;self.info_name=tk.StringVar(value='ファイル未選択')
  s=ttk.Style();s.theme_use('clam');s.configure('.',font=('Yu Gothic UI',10));s.configure('Title.TLabel',font=('Yu Gothic UI',21,'bold'))
  out=ttk.Frame(root,padding=14);out.pack(fill='both',expand=True);ttk.Label(out,text='きういファイル金庫',style='Title.TLabel').pack(anchor='w');ttk.Label(out,text='写真や書類をパスワードで暗号化。元ファイルを残したまま、PC内で処理します。').pack(anchor='w',pady=(0,9));self.book=ttk.Notebook(out);self.book.pack(fill='both',expand=True);self.file_tab=ttk.Frame(self.book,padding=12);self.key_tab=ttk.Frame(self.book,padding=12);self.info_tab=ttk.Frame(self.book,padding=12)
  for frame,label in [(self.file_tab,'ファイルを暗号化・復号'),(self.key_tab,'鍵の作成・公開鍵の取り出し'),(self.info_tab,'暗号化ファイルの情報')]:self.book.add(frame,text=label)
  self.build_files();self.build_keys();self.build_info()
  self.logbox=tk.Text(out,height=3,wrap='word',state='disabled');self.logbox.pack(fill='x',pady=8);f=ttk.Frame(out);f.pack(fill='x');ttk.Label(f,textvariable=self.status,wraplength=820).pack(side='left',fill='x',expand=True);self.button(f,'保存先を開く',self.open_folder).pack(side='right',padx=5);self.stop=ttk.Button(f,text='停止',command=self.cancel.set,state='disabled');self.stop.pack(side='right');self.progress=ttk.Progressbar(out,mode='indeterminate');self.progress.pack(fill='x',pady=(5,0))
  root.bind('<F4>',lambda e:self.guard(self.add));root.bind('<F5>',lambda e:self.guard(self.run_files) if self.book.index('current')==0 else None);root.protocol('WM_DELETE_WINDOW',self.close);root.after(70,self.poll)
 def button(self,p,label,fn):return ttk.Button(p,text=label,command=lambda:self.guard(fn))
 def guard(self,fn):
  if self.busy:return
  try:fn()
  except Exception as e:messagebox.showerror('確認してください',str(e),parent=self.root)
 def build_files(self):
  f=ttk.Frame(self.file_tab);f.pack(fill='x')
  for label,op in [('暗号化する','encrypt'),('元に戻す（復号）','decrypt')]:ttk.Radiobutton(f,text=label,variable=self.op,value=op,command=self.options_changed).pack(side='left',padx=(0,14))
  ttk.Label(f,text='方式').pack(side='left');combo=ttk.Combobox(f,textvariable=self.auth,values=['パスワード','公開鍵・秘密鍵'],state='readonly',width=18);combo.pack(side='left',padx=7);combo.bind('<<ComboboxSelected>>',lambda e:self.options_changed());self.armor_box=ttk.Checkbutton(f,text='テキスト形式（暗号化時のみ）',variable=self.armor);self.armor_box.pack(side='left',padx=12)
  f=ttk.Frame(self.file_tab);f.pack(fill='x',pady=9)
  for label,fn in [('ファイルを追加（F4）',self.add),('一覧をクリア',self.clear),('保存先を選ぶ',self.choose_base)]:self.button(f,label,fn).pack(side='left',padx=(0,6))
  ttk.Label(f,textvariable=self.dest).pack(side='left',padx=8)
  self.files=ttk.Treeview(self.file_tab,columns=('name','size','status'),show='headings',height=6)
  for name,label,width in [('name','対象ファイル（32件まで）',600),('size','サイズ',100),('status','結果',200)]:self.files.heading(name,text=label);self.files.column(name,width=width,stretch=name=='name')
  self.files.pack(fill='both',expand=True)
  self.pass_frame=ttk.Frame(self.file_tab);self.pass_frame.pack(fill='x',pady=9);ttk.Label(self.pass_frame,text='パスワード').grid(row=0,column=0,sticky='w');self.pass_entry=ttk.Entry(self.pass_frame,textvariable=self.passphrase,show='●',width=34);self.pass_entry.grid(row=0,column=1,padx=7);ttk.Label(self.pass_frame,text='もう一度（暗号化時）').grid(row=0,column=2);self.confirm_entry=ttk.Entry(self.pass_frame,textvariable=self.confirm,show='●',width=30);self.confirm_entry.grid(row=0,column=3,padx=7)
  f=ttk.Frame(self.pass_frame);f.grid(row=1,column=0,columnspan=4,sticky='w',pady=5);ttk.Checkbutton(f,text='パスワードを表示',variable=self.reveal,command=self.reveal_password).pack(side='left');self.button(f,'24文字のパスワードを作る',self.random_password).pack(side='left',padx=8);self.button(f,'パスワードをコピー',self.copy_password).pack(side='left');ttk.Label(f,text='暗号化は12文字以上。忘れると復号できません。').pack(side='left',padx=8)
  self.key_frame=ttk.LabelFrame(self.file_tab,text='公開鍵・秘密鍵で渡す',padding=8);ttk.Label(self.key_frame,text='暗号化は相手の公開鍵、復号は自分の秘密鍵を指定します。複数の宛先・SSH鍵も使えます。').pack(anchor='w');self.recipients=tk.Text(self.key_frame,height=3,width=70,wrap='word');self.recipients.pack(fill='x',pady=4)
  f=ttk.Frame(self.key_frame);f.pack(fill='x')
  self.button(f,'宛先ファイルを選ぶ',lambda:self.pick_keys('recipients')).pack(side='left');ttk.Label(f,textvariable=self.rec_label).pack(side='left',padx=6);self.button(f,'秘密鍵を選ぶ',lambda:self.pick_keys('identities')).pack(side='left',padx=6);ttk.Label(f,textvariable=self.id_label).pack(side='left');self.button(f,'鍵の指定をクリア',self.clear_keys).pack(side='right')
  f=ttk.Frame(self.key_frame);f.pack(fill='x',pady=5);ttk.Label(f,text='秘密鍵ファイルのパスワード（必要な場合）').pack(side='left');ttk.Entry(f,textvariable=self.keypass,show='●',width=28).pack(side='left',padx=7);ttk.Checkbutton(f,text='指定した秘密鍵も宛先に使う',variable=self.to_identity).pack(side='left',padx=5)
  f=ttk.Frame(self.file_tab);f.pack(fill='x',pady=(7,0));self.button(f,'処理して新しいフォルダーへ保存（F5）',self.run_files).pack(side='left');ttk.Label(f,text='元ファイルは削除・上書きしません。フォルダーは先にZIPにまとめてください。').pack(side='left',padx=12)
  ttk.Label(self.file_tab,text='ファイル名は暗号化されません。パスワードや秘密鍵は送信・自動保存しません。処理後は入力欄から消します。').pack(anchor='w',pady=5)
 def build_keys(self):
  p=self.key_tab;ttk.Label(p,text='公開鍵は相手へ渡せます。秘密鍵は自分だけで保管してください。紛失すると復号できません。').pack(anchor='w',pady=(0,10));f=ttk.Frame(p);f.pack(fill='x');ttk.Label(f,text='新しい鍵の形式').pack(side='left');ttk.Combobox(f,textvariable=self.keykind,values=['X25519（互換性重視）','PQハイブリッド（age 1.3以降）'],state='readonly',width=35).pack(side='left',padx=8);ttk.Checkbutton(f,text='秘密鍵ファイルをパスワードで保護する',variable=self.protect).pack(side='left',padx=8)
  f=ttk.Frame(p);f.pack(fill='x',pady=9);ttk.Label(f,text='保護用パスワード').grid(row=0,column=0);ttk.Entry(f,textvariable=self.genpass,show='●',width=30).grid(row=0,column=1,padx=7);ttk.Label(f,text='もう一度').grid(row=0,column=2);ttk.Entry(f,textvariable=self.genconfirm,show='●',width=30).grid(row=0,column=3,padx=7)
  f=ttk.Frame(p);f.pack(fill='x');self.button(f,'保護用パスワードを作る',self.random_key_password).pack(side='left');self.button(f,'保護用パスワードをコピー',lambda:self.copy_value(self.genpass.get(),'保護用パスワード')).pack(side='left',padx=7);self.button(f,'新しい秘密鍵を保存する',self.keygen).pack(side='left',padx=7)
  ttk.Separator(p).pack(fill='x',pady=17);f=ttk.Frame(p);f.pack(fill='x');self.button(f,'age形式の秘密鍵を選ぶ',lambda:self.pick_keys('derive')).pack(side='left');ttk.Label(f,textvariable=self.derive_label).pack(side='left',padx=8)
  f=ttk.Frame(p);f.pack(fill='x',pady=9);ttk.Label(f,text='秘密鍵ファイルのパスワード（必要な場合）').pack(side='left');ttk.Entry(f,textvariable=self.keypass,show='●',width=30).pack(side='left',padx=8);self.button(f,'公開鍵を取り出す',self.derive).pack(side='left',padx=8)
  ttk.Label(p,text='公開鍵（相手に渡す文字列）').pack(anchor='w',pady=(12,4));self.public=tk.Text(p,height=7,wrap='word',state='disabled');self.public.pack(fill='both',expand=True);f=ttk.Frame(p);f.pack(fill='x',pady=8);self.button(f,'公開鍵をコピー',lambda:self.copy_value(self.public.get('1.0','end-1c'),'公開鍵')).pack(side='left');self.button(f,'公開鍵をTXT保存',self.save_public).pack(side='left',padx=8)
 def build_info(self):
  p=self.info_tab;ttk.Label(p,text='形式や宛先の種類を表示します。内容の正しさ・改ざんの検証には復号が必要です。').pack(anchor='w');f=ttk.Frame(p);f.pack(fill='x',pady=12);self.button(f,'暗号化ファイルを選ぶ',self.pick_info).pack(side='left');ttk.Label(f,textvariable=self.info_name).pack(side='left',padx=9);self.button(f,'情報を表示',self.inspect).pack(side='left',padx=9);self.button(f,'JSONを保存',self.save_info).pack(side='left');self.info_text=tk.Text(p,wrap='word',height=17,state='disabled');self.info_text.pack(fill='both',expand=True)
 def options_changed(self):
  if self.auth.get()=='パスワード':self.key_frame.pack_forget();self.pass_frame.pack(fill='x',pady=9,before=self.file_tab.winfo_children()[-2])
  else:self.pass_frame.pack_forget();self.key_frame.pack(fill='x',pady=9,before=self.file_tab.winfo_children()[-2])
  self.confirm_entry.configure(state='normal' if self.op.get()=='encrypt' else 'disabled');self.armor_box.configure(state='normal' if self.op.get()=='encrypt' else 'disabled')
 def reveal_password(self):
  for entry in [self.pass_entry,self.confirm_entry]:entry.configure(show='' if self.reveal.get() else '●')
 def random_password(self):p=generate_password();self.passphrase.set(p);self.confirm.set(p)
 def random_key_password(self):p=generate_password();self.genpass.set(p);self.genconfirm.set(p)
 def copy_value(self,text,label):
  if not text:raise ValueError(label+'がありません。')
  self.root.clipboard_clear();self.root.clipboard_append(text);self.log(label+'をコピーしました。')
 def copy_password(self):self.copy_value(self.passphrase.get(),'パスワード')
 def add(self):self.book.select(0);self.add_paths(filedialog.askopenfilenames(parent=self.root,title='対象ファイルを追加'))
 def add_paths(self,paths):
  combined=list(dict.fromkeys([*self.paths,*[str(Path(p).resolve()) for p in paths]]))
  if len(combined)>32:raise ValueError('一度に32件までです。')
  self.paths=combined;self.files.delete(*self.files.get_children())
  for i,p in enumerate(self.paths):self.files.insert('','end',iid=str(i),values=(Path(p).name,f'{Path(p).stat().st_size/1024/1024:.1f} MiB','未処理'))
 def clear(self):self.paths=[];self.files.delete(*self.files.get_children())
 def choose_base(self):
  path=filedialog.askdirectory(parent=self.root,title='保存先の親フォルダー')
  if path:self.base=path;self.dest.set('保存先：'+Path(path).name)
 def pick_keys(self,kind):
  paths=filedialog.askopenfilenames(parent=self.root,title='鍵ファイルを選択')
  if not paths:return
  if len(paths)>16:raise ValueError('鍵ファイルは16件までです。')
  names='、'.join(Path(p).name for p in paths)[:90]
  if kind=='recipients':self.recipient_files=list(paths);self.rec_label.set('宛先：'+names)
  elif kind=='identities':self.identity_files=list(paths);self.id_label.set('秘密鍵：'+names)
  else:self.derive_ids=list(paths);self.derive_label.set('秘密鍵：'+names);self.clear_public()
 def clear_keys(self):self.recipient_files=[];self.identity_files=[];self.rec_label.set('宛先ファイル：なし');self.id_label.set('秘密鍵：なし');self.recipients.delete('1.0','end');self.keypass.set('');self.to_identity.set(False)
 def run_files(self):
  if not self.paths or not self.base:raise ValueError('対象ファイルと保存先の親フォルダーを選んでください。')
  op=self.op.get();options={'op':op,'armor':self.armor.get() if op=='encrypt' else False}
  if self.auth.get()=='パスワード':
   options['password']=runner.password(self.passphrase.get(),op=='encrypt')
   if op=='encrypt' and self.confirm.get()!=options['password']:raise ValueError('2つのパスワードが一致しません。')
  else:
   if op=='encrypt':
    options.update(recipients=self.recipients.get('1.0','end').strip(),recipient_files=list(self.recipient_files),to_identity=self.to_identity.get())
    if not options['recipients'] and not options['recipient_files'] and not options['to_identity']:raise ValueError('相手の公開鍵か宛先ファイルを指定してください。')
   if op=='decrypt' or self.to_identity.get():
    if not self.identity_files:raise ValueError('自分の秘密鍵を選んでください。')
    options.update(identity_files=list(self.identity_files),key_password=self.keypass.get())
  paths=list(self.paths);self.folder=str(runner.new_folder(self.base,op))
  for i in range(len(paths)):self.files.set(str(i),'status','待機')
  def item(result,error):self.events.put(('item',(result,error),None))
  def done(report):
   n=len(report['items']);self.log(f'{n}件を保存しました。'+('\n'+'\n'.join(report['errors']) if report['errors'] else '')+('\n停止しました。完了したファイルは残っています。' if report['stopped'] else ''));self.status.set('一部のファイルを処理できませんでした。' if report['errors'] else ('停止しました。' if report['stopped'] else '保存が終わりました。'))
  self.launch('暗号化' if op=='encrypt' else '復号',lambda:runner.batch(paths,self.folder,options,self.cancel,item),done)
 def set_public(self,packet):
  self.public.configure(state='normal');self.public.delete('1.0','end');self.public.insert('1.0',packet['public']);self.public.configure(state='disabled');self.log('公開鍵を表示しました。秘密鍵ファイルは自分だけで保管してください。')
 def clear_public(self):self.public.configure(state='normal');self.public.delete('1.0','end');self.public.configure(state='disabled')
 def keygen(self):
  protected=self.protect.get();password=''
  if protected:
   password=runner.password(self.genpass.get(),True)
   if self.genconfirm.get()!=password:raise ValueError('保護用パスワードが一致しません。')
  path=filedialog.asksaveasfilename(parent=self.root,title='秘密鍵の保存先',defaultextension='.age' if protected else '.txt',initialfile='kiwi-secret-key.age' if protected else 'kiwi-secret-key.txt')
  if not path:return
  self.clear_public();self.folder=str(Path(path).parent);request={'op':'keygen','key_kind':'pq' if self.keykind.get().startswith('PQ') else 'x25519','protect_key':protected,'password':password};self.launch('秘密鍵の作成',lambda:runner.save(request,path,self.cancel),self.set_public)
 def derive(self):
  if not self.derive_ids:raise ValueError('秘密鍵を選んでください。')
  self.clear_public();request={'op':'public','identity_files':list(self.derive_ids),'key_password':self.keypass.get()};self.launch('公開鍵の取り出し',lambda:runner.bridge(request,self.cancel),self.set_public)
 def save_public(self):
  text=self.public.get('1.0','end-1c')
  if not text:raise ValueError('公開鍵がありません。')
  path=filedialog.asksaveasfilename(parent=self.root,defaultextension='.txt',initialfile='kiwi-public-key.txt')
  if path:save_new(path,(text+'\n').encode('utf8'));self.folder=str(Path(path).parent);self.log('公開鍵を保存しました。')
 def pick_info(self):
  path=filedialog.askopenfilename(parent=self.root,title='暗号化ファイルを選択')
  if path:self.info_path=path;self.info_name.set(Path(path).name);self.inspected=None;self.info_text.configure(state='normal');self.info_text.delete('1.0','end');self.info_text.configure(state='disabled')
 def inspect(self):
  if not self.info_path:raise ValueError('暗号化ファイルを選んでください。')
  path=self.info_path
  def done(result):self.inspected=result;self.info_text.configure(state='normal');self.info_text.delete('1.0','end');self.info_text.insert('1.0',json.dumps(result,ensure_ascii=False,indent=2));self.info_text.configure(state='disabled')
  self.launch('形式の確認',lambda:runner.inspect(path,self.cancel),done)
 def save_info(self):
  if self.inspected is None:raise ValueError('先に情報を表示してください。')
  path=filedialog.asksaveasfilename(parent=self.root,defaultextension='.json',initialfile='暗号化ファイルの情報.json')
  if path:save_new(path,json.dumps(self.inspected,ensure_ascii=False,indent=2).encode('utf8'));self.folder=str(Path(path).parent)
 def launch(self,label,fn,done):
  self.busy=True;self.cancel.clear();self.status.set(label+'…');self.stop.configure(state='normal');self.progress.start()
  def work():
   try:self.events.put(('done',fn(),done))
   except Exception as e:self.events.put(('error',str(e),None))
  threading.Thread(target=work,daemon=True).start()
 def log(self,text):self.logbox.configure(state='normal');self.logbox.delete('1.0','end');self.logbox.insert('1.0',str(text)[:12000]);self.logbox.configure(state='disabled')
 def poll(self):
  try:
   event,result,done=self.events.get_nowait()
   if event=='item':
    item,error=result
    if item:
     self.files.set(str(item['index']-1),'status','保存済み')
     self.status.set(item['input']+'：保存しました。')
    elif error:self.files.set(str(error['index']-1),'status','失敗');self.log(error['message'])
   else:
    self.busy=False;self.progress.stop();self.stop.configure(state='disabled')
    for var in [self.passphrase,self.confirm,self.keypass,self.genpass,self.genconfirm]:var.set('')
    self.reveal.set(False);self.reveal_password()
    if event=='done':
     self.status.set('処理が終わりました。')
     try:done(result)
     except Exception as e:self.log(str(e));self.status.set('結果を表示できませんでした。')
    else:
     self.log(result);self.status.set('停止しました。' if self.cancel.is_set() else '処理できませんでした。')
     if not self.cancel.is_set() and not self.closing:messagebox.showerror('処理できませんでした',result,parent=self.root)
  except queue.Empty:pass
  if self.closing and not self.busy:self.root.destroy();return
  self.root.after(70,self.poll)
 def open_folder(self):
  if self.folder and Path(self.folder).is_dir():os.startfile(self.folder)
 def close(self):
  if self.busy:self.cancel.set();self.closing=True;self.status.set('停止を待っています…')
  else:self.root.destroy()

if __name__=='__main__':App(tk.Tk()).root.mainloop()
