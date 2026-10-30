"""Visible PDF text, logo and page overlays."""
import sys,threading
from pathlib import Path
import tkinter as tk
from tkinter import ttk,filedialog,messagebox
if not getattr(sys,'frozen',False):sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'common'))
from consumer_ui import Window
import core

class App(Window):
 def __init__(self):
  self.worker=None
  super().__init__('きういPDFスタンプ','確認用の文字、ロゴ、ページ番号などをPDFに重ねます。元ファイルを残して別名で保存します。',core.ENGINE)
  self.geometry('1120x960');self.minsize(1000,900)
  self.field('input','元のPDF',picker=[('PDF','*.pdf')])
  self.field('action','操作','追加',['追加','更新','削除'])
  self.field('layer','重ね方','手前（スタンプ）',['手前（スタンプ）','背面（透かし）'])
  self.field('kind','重ねる内容','日本語の文字（画像化）',['日本語の文字（画像化）','欧文・ページ番号','画像','PDFの指定ページ','PDFを順番に重ねる'])
  self.field('text','文字（改行は \\n、欧文のページ番号は %p / %P）','確認用')
  self.field('mark','ロゴ画像／重ねるPDF',picker=[('画像・PDF','*.png *.jpg *.jpeg *.webp *.tif *.tiff *.pdf')])
  self.field('markpage','重ねるPDFのページ（指定ページモード）','1')
  self.field('pages','対象ページ（空欄は全部、例: 1-3,5 / odd / even）','')
  self.field('position','位置','中央',list(core.POSITIONS))
  self.field('scale','幅の割合（0.01～1）','0.5')
  self.field('rotation','回転（-180～180度）','-30')
  self.field('opacity','濃さ（0.01～1）','0.3')
  self.field('extra','詳細設定（欧文・画像・PDF用JSON、ヘルプ参照）','{}')
  self.button(self.actions,'別名でPDFを保存（F5）',self.process).pack(side='left')
  self.button(self.actions,'ヘルプ',self.help).pack(side='right')
  self.button(self.actions,'エンジン情報',self.version).pack(side='right',padx=8)
  self.output.configure(height=4)
  self.note.set('PDFは32 MiB・1000ページまで、画像・重ねるPDFは16 MiBまで。暗号化・電子署名付きPDFは対象外です。\n透かしはコピー・編集を防ぎません。背面は元の画像に隠れることがあります。保存後に表示を確認してください。')
  self.status.set('初回にエンジンを準備し、元のPDFと重ねる内容を選んでください。')
  self.bind('<F4>',lambda event:self.pick());self.bind('<F5>',lambda event:self.process());self.bind('<Alt-F4>',lambda event:(self.close(),'break')[1])
 def start(self,job,done):
  if self.busy or self.closing:return
  self.busy=True;self.cancel.clear()
  for widget,_ in self.controls:widget.configure(state='disabled')
  self.stop.configure(state='normal');self.status.set('処理しています…')
  def work():
   try:self.events.put(('done',(done,job())))
   except Exception as exc:self.events.put(('error',str(exc)))
  self.worker=threading.Thread(target=work,daemon=False);self.worker.start()
 def destroy(self):
  if self.worker is not None and self.worker.is_alive():
   self.closing=True;self.cancel.set();self.after(20,self.destroy);return
  for timer in self.tk.call('after','info'):self.after_cancel(timer)
  tk.Tk.destroy(self)
 def pick(self):
  if self.busy:return
  path=filedialog.askopenfilename(parent=self,title='元のPDFを選ぶ',filetypes=[('PDF','*.pdf')])
  if path:self.vars['input'].set(path)
 def process(self):
  if self.busy:return
  v=self.values()
  if not v['input']:messagebox.showerror('元のPDF','PDFを選んでください。',parent=self);return
  if v['action'] in {'更新','削除'} and not messagebox.askyesno('操作の確認','pdfcpu形式の既存の印を対象ページから取り除きます。手作業の印や他のPDFソフトの印は除去できない場合があります。続けますか？',parent=self):return
  folder=self.choose_save()
  if folder:
   v['text']=v['text'].replace('\\n','\n')
   self.start(lambda:core.run(v,folder,self.cancel),self.receive)
 def receive(self,result):
  self.show(f"保存しました: {Path(result['path']).name}\n{result['pages']}ページ / {result['bytes']:,} bytes\n元のPDFは変更していません。保存したPDFをビューアーで開き、重なりや文字の表示を確認してください。")
  self.status.set('保存しました。PDFの見た目を確認してください。')
 def version(self):
  if not self.busy:self.start(lambda:core.version(self.cancel),lambda value:self.show(value))
 def help(self):
  top=tk.Toplevel(self);top.title('PDFスタンプのヘルプ');top.geometry('850x680')
  text=tk.Text(top,wrap='word');text.pack(fill='both',expand=True)
  text.insert('1.0',(core.ROOT/'README.txt').read_text(encoding='utf8')+'\n\n'+(core.ROOT/'upstream-help.txt').read_text(encoding='utf8'));text.configure(state='disabled')

if __name__=='__main__':App().mainloop()
