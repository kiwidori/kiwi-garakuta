"""Inspect unknown file types without launching or modifying files."""
import json,sys,threading
from pathlib import Path
import tkinter as tk
from tkinter import ttk,filedialog,messagebox
if not getattr(sys,'frozen',False):sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'common'))
from consumer_ui import Window
import core

class App(Window):
 def __init__(self):
  self.paths=[];self.result=None;self.worker=None;self.traces=[]
  super().__init__('きういファイルしらべ','拡張子がない・間違っていそうなファイルを、内容から調べます。元のファイルは変更しません。',core.ENGINE)
  self.geometry('1160x910');self.minsize(1040,820)
  self.mode=self.field('mode','調べるもの','ファイル／フォルダー',['ファイル／フォルダー','入力した文章','ファイルを標準入力へ'])
  buttons=ttk.Frame(self.body);buttons.pack(before=self.actions,fill='x',pady=4)
  self.button(buttons,'ファイルを選ぶ（F4）',self.pick).pack(side='left')
  self.button(buttons,'フォルダーを選ぶ',self.pick_folder).pack(side='left',padx=8)
  self.button(buttons,'選択をクリア',self.clear).pack(side='left')
  self.recursive=tk.BooleanVar(master=self,value=False)
  checkbox=ttk.Checkbutton(buttons,text='下の階層も調べる',variable=self.recursive,command=self.invalidate);checkbox.pack(side='left',padx=12);self.controls.append((checkbox,'normal'))
  self.files=tk.Listbox(self.body,height=3);self.files.pack(before=self.actions,fill='x');self.controls.append((self.files,'normal'))
  ttk.Label(self.body,text='文章を調べる場合は下に入力（UTF-8で2 MiBまで）。標準入力ファイルは上の一覧で1件選びます。').pack(before=self.actions,anchor='w')
  self.text=tk.Text(self.body,height=3,wrap='word');self.text.pack(before=self.actions,fill='x');self.controls.append((self.text,'normal'))
  self.text.bind('<<Modified>>',self.text_changed)
  self.kind=self.field('kind','結果の表示・保存形式','CSV',['CSV','JSON','JSONL','説明','MIME','ラベル','書式指定'])
  self.pattern=self.field('pattern','書式指定の内容','%p: %d (%m) [%S]')
  self.button(self.actions,'種類を調べる（F5）',self.analyze).pack(side='left')
  self.button(self.actions,'表示を更新',self.display).pack(side='left',padx=8)
  self.button(self.actions,'結果を別名で保存',self.save).pack(side='left')
  self.button(self.actions,'同梱ヘルプ',self.help).pack(side='right')
  self.button(self.actions,'エンジン情報',self.version).pack(side='right',padx=8)
  self.table=ttk.Treeview(self.body,columns=('name','type','ext','mime','score'),show='headings',height=7)
  for key,title,width in [('name','ファイル',230),('type','推定される種類',240),('ext','候補拡張子',140),('mime','MIME',260),('score','推定スコア',100)]:self.table.heading(key,text=title);self.table.column(key,width=width)
  self.table.pack(before=self.output,fill='x',pady=8);self.output.configure(height=6)
  self.note.set('判定は推定です。ウイルス検査やファイルの修復は行いません。通常ファイル500件・各2 GiB・合計20 GiBまで。\nエンジンは初回約10 MBを公式配布から取得。Microsoft Visual C++ v14 x64ランタイムが必要です。')
  self.status.set('ファイルやフォルダーを選んで「種類を調べる」を押してください。')
  self.traces.append((self.mode,self.mode.trace_add('write',lambda *args:self.invalidate())))
  self.bind('<F4>',lambda event:self.pick());self.bind('<F5>',lambda event:self.analyze());self.bind('<Alt-F4>',lambda event:(self.close(),'break')[1])
 def start(self,job,done):
  if self.busy or self.closing:return
  self.busy=True;self.cancel.clear()
  for widget,_ in self.controls:widget.configure(state='disabled')
  self.stop.configure(state='normal');self.status.set('処理しています…')
  def work():
   try:self.events.put(('done',(done,job())))
   except Exception as exc:self.events.put(('error',str(exc)))
  self.worker=threading.Thread(target=work,daemon=False);self.worker.start()
 def setup(self):
  self.start(lambda:core.ENGINE.install(self.cancel,lambda msg:self.events.put(('status',msg))),lambda result:self.status.set('準備できました。ファイルの判定はPC内で行います。'))
 def destroy(self):
  if self.worker is not None and self.worker.is_alive():
   self.closing=True;self.cancel.set();self.after(20,self.destroy);return
  for timer in self.tk.call('after','info'):self.after_cancel(timer)
  for var,token in self.traces:var.trace_remove('write',token)
  self.traces=[];tk.Tk.destroy(self)
 def text_changed(self,event=None):
  if self.text.edit_modified():self.text.edit_modified(False);self.invalidate()
 def invalidate(self):
  self.result=None
  if hasattr(self,'table'):self.table.delete(*self.table.get_children());self.show('')
 def pick(self):
  if self.busy:return
  values=filedialog.askopenfilenames(parent=self,title='調べるファイルを選ぶ（200件まで）')
  if values:self.set_paths(values)
 def pick_folder(self):
  if self.busy:return
  value=filedialog.askdirectory(parent=self,title='調べるフォルダーを選ぶ')
  if value:self.set_paths([value])
 def set_paths(self,values):
  if self.busy:return
  if len(values)>200:messagebox.showerror('選択件数','200件まで選べます。',parent=self);return
  self.invalidate();self.paths=list(values);self.files.delete(0,'end')
  for path in values:self.files.insert('end',Path(path).name)
  if values:self.files.selection_set(0)
 def clear(self):
  if not self.busy:self.set_paths([])
 def analyze(self):
  if self.busy:return
  try:
   mode=self.mode.get();data=None;paths=list(self.paths)
   if mode=='入力した文章':data=self.text.get('1.0','end-1c').encode('utf8')
   elif mode=='ファイルを標準入力へ':
    if not paths:raise ValueError('標準入力に使うファイルを選んでください。')
    path=core.safe_path(paths[(self.files.curselection() or (0,))[0]])
    with path.open('rb') as source:data=source.read(2*1024**2+1)
   elif mode!='ファイル／フォルダー':raise ValueError('入力方法を選んでください。')
   if data is not None and len(data)>2*1024**2:raise ValueError('標準入力は2 MiBまでです。')
   recursive=self.recursive.get();self.invalidate()
   self.start(lambda:core.inspect(paths,recursive,self.cancel,stdin=data),self.receive)
  except Exception as exc:messagebox.showerror('入力の確認',str(exc),parent=self)
 def receive(self,result):
  self.result=result
  for record in result['records']:
   path,description,extensions,mime,label,group,score=core.row(record)
   self.table.insert('','end',values=(Path(path).name if path!='-' else '標準入力',description,extensions,mime,score))
  self.status.set(f"{len(result['records'])}件を調べました。リンク・アクセス不可・対象外の項目など{result['skipped']}件を除外しました。")
  self.display()
 def display(self):
  if self.busy or not self.result:return
  try:self.show(core.report(self.result,self.kind.get(),self.pattern.get()))
  except Exception as exc:messagebox.showerror('表示書式',str(exc),parent=self)
 def save(self):
  if self.busy or not self.result:return
  folder=self.choose_save()
  if not folder:return
  result=self.result;kind=self.kind.get();pattern=self.pattern.get()
  self.start(lambda:core.save(result,kind,pattern,folder,self.cancel),lambda path:self.status.set('結果を保存しました: '+path.name))
 def help(self):
  top=tk.Toplevel(self);top.title('ファイルしらべのヘルプ');top.geometry('850x650')
  text=tk.Text(top,wrap='word');text.pack(fill='both',expand=True)
  helptext=(core.ROOT/'upstream-help.txt').read_text(encoding='utf8')
  text.insert('1.0','書式: %p パス / %l ラベル / %d 説明 / %g 分類 / %m MIME / %e 拡張子候補 / %s スコア / %S 百分率 / %b 補正前のモデル判定 / %% %記号\n\nJSON・JSONLは元の判定内容を保持します。書式指定は表示用で、元CLIと数値表記が異なる場合があります。\n\n'+helptext);text.configure(state='disabled')
 def version(self):
  if not self.busy:self.start(lambda:core.version(self.cancel),lambda value:messagebox.showinfo('エンジン情報',value,parent=self))

if __name__=='__main__':App().mainloop()
