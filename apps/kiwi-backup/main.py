"""Portable interface for local encrypted backups."""
import json,os,queue,socket,sys,threading,tkinter as tk
from pathlib import Path
from tkinter import ttk,filedialog,messagebox,simpledialog
sys.path.insert(0,str(Path(__file__).resolve().parent.parent/'common'))
import core
from runtime import resource_path

def readable(n):
 n=float(n or 0)
 for unit in ('B','KiB','MiB','GiB','TiB'):
  if n<1024:return f'{n:,.1f} {unit}'
  n/=1024
 return f'{n:,.1f} PiB'

class App:
 def __init__(self,root):
  self.root=root;root.title('きういバックアップ');root.geometry('1150x860');root.minsize(1000,760)
  self.events=queue.Queue();self.cancel=threading.Event();self.busy=False;self.closing=False;self.options={};self.rows={};self.nodes={};self.browsed=None;self.plan=None;self.last_folder=None
  self.repo=tk.StringVar();self.password=tk.StringVar();self.tag=tk.StringVar();self.host=tk.StringVar(value=socket.gethostname());self.pattern=tk.StringVar(value='*.jpg');self.keep=tk.StringVar(value='5');self.deep=tk.BooleanVar(value=True);self.status=tk.StringVar(value='バックアップ先とパスワードを指定してください。')
  style=ttk.Style();style.theme_use('clam');style.configure('.',font=('Yu Gothic UI',10));style.configure('Title.TLabel',font=('Yu Gothic UI',20,'bold'))
  outer=ttk.Frame(root,padding=16);outer.pack(fill='both',expand=True)
  ttk.Label(outer,text='きういバックアップ',style='Title.TLabel').pack(anchor='w')
  ttk.Label(outer,text='写真や書類を、履歴ごとに。パスワードで暗号化して外付けドライブなどへ保存します。').pack(anchor='w',pady=(0,10))
  top=ttk.Frame(outer);top.pack(fill='x');top.columnconfigure(1,weight=1)
  ttk.Label(top,text='バックアップ先（保管庫）').grid(row=0,column=0,sticky='w');ttk.Entry(top,textvariable=self.repo).grid(row=0,column=1,sticky='ew',padx=6)
  self.button(top,'選ぶ',self.choose_repo).grid(row=0,column=2)
  ttk.Label(top,text='パスワード').grid(row=1,column=0,sticky='w',pady=6);self.pwentry=ttk.Entry(top,textvariable=self.password,show='●');self.pwentry.grid(row=1,column=1,sticky='ew',padx=6)
  self.show=tk.BooleanVar();ttk.Checkbutton(top,text='表示',variable=self.show,command=lambda:self.pwentry.configure(show='' if self.show.get() else '●')).grid(row=1,column=2)
  bar=ttk.Frame(outer);bar.pack(fill='x',pady=5)
  for label,cmd in [('新しい保管庫を作る',self.init),('保存履歴を読む',self.load),('詳細設定',self.advanced),('CLIヘルプ',self.help)]:self.button(bar,label,cmd).pack(side='left',padx=(0,6))
  book=ttk.Notebook(outer);book.pack(fill='both',expand=True,pady=5);self.book=book
  save=ttk.Frame(book,padding=10);history=ttk.Frame(book,padding=10);maint=ttk.Frame(book,padding=10)
  for tab,name in [(save,'保存する'),(history,'履歴から戻す'),(maint,'点検・整理')]:book.add(tab,text=name)
  ttk.Label(save,text='保存するファイル・フォルダー（1行に1件、32件まで）').pack(anchor='w')
  self.sources=tk.Text(save,height=7,wrap='none');self.sources.pack(fill='x',pady=5)
  b=ttk.Frame(save);b.pack(fill='x')
  self.button(b,'フォルダーを追加',lambda:self.add_source(True)).pack(side='left');self.button(b,'ファイルを追加',lambda:self.add_source(False)).pack(side='left',padx=5)
  ttk.Label(save,text='除外する名前・パターン（1行に1件。例：*.tmp）').pack(anchor='w',pady=(12,0))
  self.exclude=tk.Text(save,height=3);self.exclude.pack(fill='x',pady=5)
  fields=ttk.Frame(save);fields.pack(fill='x')
  for col,(label,var) in enumerate([('タグ（任意・カンマ区切り）',self.tag),('このPCの名前',self.host)]):
   ttk.Label(fields,text=label).grid(row=0,column=col,sticky='w');ttk.Entry(fields,textvariable=var,width=42).grid(row=1,column=col,sticky='ew',padx=(0,8));fields.columnconfigure(col,weight=1)
  self.button(save,'バックアップを保存',self.save).pack(anchor='w',pady=14)
  ttk.Label(save,text='パスワードは保存しません。忘れると復元できません。\nPC故障に備えるには、別のドライブや外付け媒体を保管庫に指定してください。',wraplength=1000).pack(anchor='w')
  self.tree=self.make_tree(history,('日時','保存元','タグ','ファイル数','容量'),height=5,widths=(170,400,140,90,100));self.tree.bind('<<TreeviewSelect>>',self.selection_changed)
  b=ttk.Frame(history);b.pack(fill='x',pady=5)
  for label,cmd in [('中身を見る',self.browse),('履歴全体を復元',lambda:self.restore(False,False)),('2件を比較',lambda:self.action('diff')),('容量',lambda:self.action('stats')),('タグを編集',self.tags),('別の保管庫へ複製',self.copy)]:self.button(b,label,cmd).pack(side='left',padx=(0,4))
  f=ttk.Frame(history);f.pack(fill='x',pady=3);ttk.Label(f,text='履歴内の名前検索').pack(side='left');ttk.Entry(f,textvariable=self.pattern).pack(side='left',fill='x',expand=True,padx=6);self.button(f,'検索',lambda:self.action('find')).pack(side='left')
  self.files=self.make_tree(history,('履歴内のパス','種類','容量','更新日時'),height=6,widths=(600,80,90,160))
  b=ttk.Frame(history);b.pack(fill='x',pady=5)
  self.button(b,'選んだフォルダーを復元',lambda:self.restore(True,False)).pack(side='left');self.button(b,'選んだ1ファイルを取り出す',lambda:self.restore(True,True)).pack(side='left',padx=5)
  ttk.Label(history,text='復元先には毎回新しいフォルダーを作ります。元のファイルは上書きしません。',wraplength=1000).pack(anchor='w')
  ttk.Label(maint,text='保管庫のデータを検査します。大きな保管庫では時間がかかります。').pack(anchor='w')
  ttk.Checkbutton(maint,text='保存データをすべて読み出して検査する',variable=self.deep).pack(anchor='w',pady=5);self.button(maint,'検査する',self.check).pack(anchor='w')
  ttk.Separator(maint).pack(fill='x',pady=12)
  f=ttk.Frame(maint);f.pack(fill='x');ttk.Label(f,text='保存元・PCごとに最新').pack(side='left');ttk.Entry(f,textvariable=self.keep,width=6).pack(side='left',padx=5);ttk.Label(f,text='件を残す').pack(side='left');self.button(f,'整理の予定を確認',self.preview).pack(side='left',padx=8);self.button(f,'確認した履歴を削除',self.forget).pack(side='left')
  ttk.Label(maint,text='詳細設定で日・週・月単位の保持条件を追加できます。削除予定を確認した後でのみ実行できます。',wraplength=1000).pack(anchor='w',pady=8)
  f=ttk.Frame(maint);f.pack(fill='x',pady=6)
  for label,cmd in [('不要データの容量を確認',lambda:self.prune(True)),('不要データを整理',lambda:self.prune(False)),('停止後の古いロックを解除',lambda:self.action('unlock')),('暗号鍵の一覧',lambda:self.action('key'))]:self.button(f,label,cmd).pack(side='left',padx=(0,5))
  ttk.Label(maint,text='履歴の削除・不要データの整理は取り消せません。ロック解除は使用中でない古いロックだけが対象です。',wraplength=1000).pack(anchor='w',pady=8)
  self.output=tk.Text(outer,height=7,wrap='word',state='disabled');self.output.pack(fill='x',pady=5)
  bottom=ttk.Frame(outer);bottom.pack(fill='x');ttk.Label(bottom,textvariable=self.status,wraplength=850).pack(side='left',fill='x',expand=True)
  self.stop=ttk.Button(bottom,text='停止',command=self.cancel.set,state='disabled');self.stop.pack(side='right');self.button(bottom,'復元先を開く',self.open_folder).pack(side='right',padx=6)
  self.progress=ttk.Progressbar(outer,mode='indeterminate');self.progress.pack(fill='x',pady=(5,0))
  root.protocol('WM_DELETE_WINDOW',self.close);root.after(100,self.poll)

 def button(self,parent,label,cmd):return ttk.Button(parent,text=label,command=lambda:self.guard(cmd))
 def guard(self,cmd):
  if self.busy:return
  try:cmd()
  except Exception as e:messagebox.showerror('確認してください',str(e),parent=self.root)
 def make_tree(self,parent,cols,height,widths):
  f=ttk.Frame(parent);f.pack(fill='both',expand=True);tree=ttk.Treeview(f,columns=cols,show='headings',height=height)
  for c,w in zip(cols,widths):tree.heading(c,text=c);tree.column(c,width=w,stretch=True)
  y=ttk.Scrollbar(f,orient='vertical',command=tree.yview);x=ttk.Scrollbar(f,orient='horizontal',command=tree.xview);tree.configure(yscrollcommand=y.set,xscrollcommand=x.set);tree.grid(row=0,column=0,sticky='nsew');y.grid(row=0,column=1,sticky='ns');x.grid(row=1,column=0,sticky='ew');f.columnconfigure(0,weight=1);f.rowconfigure(0,weight=1);return tree
 def log(self,s):self.output.configure(state='normal');self.output.delete('1.0','end');self.output.insert('1.0',str(s)[:24000]);self.output.configure(state='disabled')
 def credentials(self):
  repo=str(core.local_repository(self.repo.get(),must_exist=False));pw=self.password.get()
  if not pw:raise ValueError('パスワードを入力してください。')
  return repo,pw
 def choose_repo(self):
  p=filedialog.askdirectory(parent=self.root,title='保管庫のフォルダー');
  if p:self.repo.set(p);self.plan=None
 def add_source(self,folder):
  paths=[filedialog.askdirectory(parent=self.root)] if folder else filedialog.askopenfilenames(parent=self.root)
  for p in paths:
   if p:self.sources.insert('end',p+'\n')
 def run(self,label,fn,done=None):
  if self.busy:return
  self.busy=True;self.cancel.clear();self.status.set(label+'…');self.progress.start();self.stop.configure(state='normal')
  def worker():
   try:self.events.put((True,fn(),done,label))
   except Exception as e:self.events.put((False,str(e),None,label))
  threading.Thread(target=worker,daemon=True).start()
 def poll(self):
  try:
   ok,result,done,label=self.events.get_nowait();self.busy=False;self.progress.stop();self.stop.configure(state='disabled')
   if ok:
    self.status.set(label+'：完了')
    try:
     if done:done(result)
     else:self.render(result)
    except Exception as e:self.log(str(e));self.status.set('結果の表示に失敗しました。')
   else:
    self.log(result);self.status.set('停止しました。途中まで変更されている場合は履歴を読み直してください。' if self.cancel.is_set() else '処理を完了できませんでした。')
    if not self.closing and not self.cancel.is_set():messagebox.showerror('処理できませんでした',result,parent=self.root)
  except queue.Empty:pass
  if self.closing and not self.busy:self.password.set('');self.root.destroy();return
  self.root.after(100,self.poll)
 def close(self):
  self.closing=True
  if self.busy:self.cancel.set();self.status.set('停止を待っています…')
  else:self.password.set('');self.root.destroy()
 def init(self):
  repo,pw=self.credentials();confirm=simpledialog.askstring('新しい保管庫','パスワードをもう一度入力してください（8文字以上）。忘れると復元できません。',show='●',parent=self.root)
  if confirm is None:return
  if pw!=confirm:raise ValueError('パスワードが一致しません。')
  self.run('保管庫の作成',lambda:core.initialize(repo,pw,self.cancel),lambda r:self.log('保管庫を作成しました。保存するファイル・フォルダーを選んでください。'))
 def display_history(self,rows):
  self.rows={s['id']:s for s in rows};self.tree.delete(*self.tree.get_children());self.clear_files();self.plan=None
  for s in rows:
   info=s.get('summary') or {};self.tree.insert('', 'end',iid=s['id'],values=(s['time'][:19].replace('T',' '),' / '.join(s.get('paths',[])),', '.join(s.get('tags',[])),info.get('total_files_processed','—'),readable(info.get('total_bytes_processed'))))
  self.log(f'保存履歴：{len(rows)}件。履歴を選択し「中身を見る」または「履歴全体を復元」を押してください。')
 def load(self):
  repo,pw=self.credentials();opts=dict(self.options.get('snapshots',{}));self.run('履歴の読み込み',lambda:core.snapshots(repo,pw,self.cancel,opts),self.display_history)
 def mutation(self,label,repo,pw,fn):
  self.plan=None
  def work():
   r=fn()
   try:return r,core.snapshots(repo,pw,self.cancel),''
   except Exception as e:return r,None,str(e)
  def done(result):
   r,rows,err=result
   if rows is not None:self.display_history(rows)
   self.render(r)
   if err:self.log('操作は終了しました。履歴の再読み込みに失敗：'+err)
  self.run(label,work,done)
 def save(self):
  repo,pw=self.credentials();sources=self.sources.get('1.0','end').strip().splitlines();exclude=self.exclude.get('1.0','end').strip().splitlines();tags=self.tag.get();host=self.host.get();opts=dict(self.options.get('backup',{}))
  if len(exclude)>64:raise ValueError('除外パターンは64件までです。')
  self.mutation('バックアップ',repo,pw,lambda:core.backup(repo,pw,sources,exclude,tags,host,opts,self.cancel))
 def selected(self,n=None):
  ids=list(self.tree.selection())
  if n is not None and len(ids)!=n:raise ValueError(f'保存履歴を{n}件選択してください。')
  return ids
 def clear_files(self):self.files.delete(*self.files.get_children());self.nodes={};self.browsed=None
 def selection_changed(self,event=None):
  if self.browsed and list(self.tree.selection())!=[self.browsed]:self.clear_files()
 def browse(self):
  repo,pw=self.credentials();sid=self.selected(1)[0];opts=dict(self.options.get('ls',{}))
  self.run('履歴の中身',lambda:core.operate(repo,pw,'ls',[sid],opts,self.cancel),lambda r:self.display_files(sid,core.records(r)))
 def display_files(self,sid,rows):
  self.clear_files();self.browsed=sid
  if isinstance(rows,dict):rows=[rows]
  nodes=[n for n in rows if isinstance(n,dict) and n.get('message_type')=='node']
  for i,n in enumerate(nodes[:50000]):
   key=str(i);self.nodes[key]=n;self.files.insert('','end',iid=key,values=(n['path'],n.get('type',''),readable(n.get('size')),n.get('mtime','')[:19]))
  self.log(f'履歴の内容：{len(nodes)}項目。表示は50,000項目までです。')
 def restore(self,scoped,single):
  repo,pw=self.credentials();sid=self.selected(1)[0];scope=''
  if scoped:
   sel=self.files.selection()
   if self.browsed!=sid or len(sel)!=1:raise ValueError('「中身を見る」で項目を1件選んでください。')
   node=self.nodes[sel[0]]
   if node.get('type')!=('file' if single else 'dir'):raise ValueError('ファイル'+'を選んでください。' if single else 'フォルダーを選んでください。')
   scope=node['path']
  parent=filedialog.askdirectory(parent=self.root,title='新しい復元フォルダーを作る場所')
  if not parent:return
  opts=dict(self.options.get('restore',{}))
  def done(r):self.last_folder=r['folder'];self.log('復元しました。\n'+r['folder'])
  self.run('復元',lambda:core.restore(repo,pw,sid,parent,self.cancel,scope,single,opts),done)
 def action(self,op,overrides=None):
  repo,pw=self.credentials();ids=self.selected(2 if op=='diff' else None);opts=dict(self.options.get(op,{}));opts.update(overrides or {});pattern=self.pattern.get()
  if op=='unlock' and not messagebox.askyesno('古いロック','別のPCも含め、この保管庫を使う処理がすべて停止していることを確認してください。古いロックを解除しますか？',parent=self.root):return
  names={'find':'名前検索','diff':'履歴の比較','stats':'容量の集計','check':'保管庫の検査','prune':'不要データの整理','unlock':'古いロックの解除','key':'暗号鍵の一覧'}
  self.run(names.get(op,op),lambda:core.operate(repo,pw,op,ids,opts,self.cancel,pattern=pattern),lambda r:self.render(r,op))
 def tags(self):
  repo,pw=self.credentials();ids=self.selected();value=simpledialog.askstring('タグ編集','付けるタグ（カンマ区切り）',parent=self.root)
  if value is None:return
  mode=simpledialog.askstring('操作','add（追加）・remove（解除）・set（置換）',initialvalue='add',parent=self.root)
  if mode is None:return
  self.mutation('タグ編集',repo,pw,lambda:core.operate(repo,pw,'tag',ids,{},self.cancel,tags=value,tag_action=mode))
 def copy(self):
  repo,pw=self.credentials();ids=self.selected()
  if not ids:raise ValueError('複製する履歴を選んでください。')
  dst=filedialog.askdirectory(parent=self.root,title='複製先の作成済み保管庫')
  if not dst:return
  dp=simpledialog.askstring('複製先','複製先のパスワード',show='●',parent=self.root)
  if not dp:return
  self.run('履歴の複製',lambda:core.copy_snapshots(repo,pw,dst,dp,ids,self.cancel))
 def check(self):self.action('check',{'read-data':self.deep.get()})
 def preview(self):
  repo,pw=self.credentials();opts={'keep-last':int(self.keep.get()),**self.options.get('forget',{})}
  def done(p):self.plan=p;self.log('削除予定：'+str(len(p['remove']))+'件\n'+'\n'.join(p['remove'])+'\n確認した履歴以外は削除しません。')
  self.run('整理の予定',lambda:core.plan_retention(repo,pw,opts,self.cancel),done)
 def forget(self):
  repo,pw=self.credentials();plan=self.plan
  if not plan or not plan['remove']:raise ValueError('先に整理の予定を確認してください。')
  if not messagebox.askyesno('履歴を削除',f"確認した{len(plan['remove'])}件の履歴を削除します。元に戻せません。実行しますか？",parent=self.root):return
  self.mutation('履歴の削除',repo,pw,lambda:core.apply_retention(repo,pw,plan,self.cancel))
 def prune(self,dry):
  if not dry and not messagebox.askyesno('不要データの整理','どの履歴からも使われない保存データを削除します。元に戻せません。実行しますか？',parent=self.root):return
  self.action('prune',{'dry-run':dry})
 def render(self,r,op=''):
  if not isinstance(r,dict) or 'stdout' not in r:self.log(str(r));return
  try:rows=core.records(r)
  except ValueError:
   if op in ('prune','unlock'):
    self.log(r['stdout'].decode('utf8',errors='replace')[-16000:]+'\n'+r.get('stderr','')[-4000:]);return
   raise
  rows=rows if isinstance(rows,list) else [rows];lines=[]
  for s in rows[:50000]:
   if not isinstance(s,dict):continue
   if op=='key':lines.append(('使用中 ' if s.get('current') else '')+str(s.get('id',''))+' '+str(s.get('created',''))[:19])
   elif op=='find':
    for n in s.get('matches',[]):lines.append(str(n.get('path',''))+'  '+readable(n.get('size')))
   elif op=='diff' and s.get('message_type')=='change':lines.append(s.get('modifier','')+' '+s.get('path',''))
   elif 'total_size' in s:lines.append('容量：'+readable(s['total_size'])+' / 項目数：'+str(s.get('total_file_count','—')))
   elif s.get('message_type')=='summary':
    if 'snapshot_id' in s:lines.append('保存しました。ファイル数：'+str(s.get('total_files_processed',0))+' / '+readable(s.get('total_bytes_processed'))+'\n履歴ID：'+s['snapshot_id'])
    elif 'num_errors' in s:lines.append('検査エラー：'+str(s['num_errors']))
  if r.get('partial'):lines.insert(0,'注意：一部のファイルを保存できませんでした。保存できた分だけの履歴です。')
  if r.get('stderr'):lines.append(r['stderr'][-8000:])
  self.log('\n'.join(lines) or '処理が終了しました。')
 def advanced(self):
  available=('backup','snapshots','ls','restore','find','diff','stats','check','forget','prune')
  op=simpledialog.askstring('詳細設定','操作：'+', '.join(available),initialvalue='backup',parent=self.root)
  if op is None:return
  if op not in available:raise ValueError('操作名を確認してください。')
  spec={**core.SCHEMA[op],**core.COMMON};win=tk.Toplevel(self.root);win.title('詳細設定：'+op);win.geometry('800x600')
  ttk.Label(win,text='JSONで指定します。例：{"compression":"fastest"}。保存は今回の起動中のみ。',wraplength=760).pack(padx=12,pady=8,anchor='w')
  ttk.Label(win,text='使える項目：'+', '.join(k+' ('+v+')' for k,v in spec.items()),wraplength=760).pack(padx=12,anchor='w')
  edit=tk.Text(win,height=12);edit.pack(fill='both',expand=True,padx=12,pady=8);edit.insert('1.0',json.dumps(self.options.get(op,{}),ensure_ascii=False,indent=2))
  def apply():
   opts=json.loads(edit.get('1.0','end'));core.flags(op,opts);self.options[op]=opts;self.plan=None;win.destroy()
  ttk.Button(win,text='適用',command=lambda:self.guard(apply)).pack(pady=8)
 def help(self):
  win=tk.Toplevel(self.root);win.title('restic CLIヘルプ');win.geometry('900x650');t=tk.Text(win,wrap='none');t.pack(fill='both',expand=True);t.insert('1.0',Path(resource_path('upstream-help.txt',core.ROOT)).read_text(encoding='utf8'));t.configure(state='disabled')
 def open_folder(self):
  if self.last_folder and Path(self.last_folder).is_dir():os.startfile(self.last_folder)

if __name__=='__main__':App(tk.Tk()).root.mainloop()
