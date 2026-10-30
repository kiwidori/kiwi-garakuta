"""Make printable name cards and storage labels from plain text."""
from pathlib import Path
import base64,os,sys,threading,tkinter as tk
from tkinter import ttk,filedialog,messagebox
if not getattr(sys,'frozen',False):sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'common'))
from consumer_ui import Window
from consumer_runtime import safe_path
import core

class App(Window):
 def __init__(self):
  self.worker=None;self.last=None
  super().__init__('きういラベル印刷','名札・収納ラベルをA4に並べて、PDFや画像に保存します。',core.ENGINE)
  self.geometry('1100x990');self.minsize(980,930)
  source=ttk.LabelFrame(self.body,text='ラベルの文字（1行で1種類、 | で3段まで）',padding=8);source.pack(fill='x',before=self.form)
  self.input=tk.Text(source,height=6,font=('Yu Gothic UI',11),wrap='none');self.input.pack(fill='x');self.input.insert('1.0','きうい | もも組 | たのしくあそぼう\nおもちゃ | 積み木・ブロック\n文房具 | のり・はさみ')
  self.controls.append((self.input,'normal'));self.button(source,'UTF-8の一覧を開く',self.load_text).pack(anchor='w',pady=(5,0))
  presets=ttk.Frame(self.body);presets.pack(fill='x',pady=7,before=self.form)
  for title,c,r in [('名札（2列×6行）',2,6),('収納ラベル（3列×8行）',3,8),('大きめ（2列×4行）',2,4)]:self.button(presets,title,lambda c=c,r=r:self.preset(c,r)).pack(side='left',padx=(0,8))
  self.button(presets,'Windowsのフォント一覧を取得',self.refresh_fonts).pack(side='left')
  for k,label,value in [('columns','列（1～4）','2'),('rows','行（1～12）','6'),('margin','用紙の余白 mm（5～25）','10'),('gap','ラベル間隔 mm（0～10）','3'),('font','文字サイズ pt（8～32・長い文字は縮小）','20'),('repeat','同じラベルの枚数（1～100）','1')]:self.field(k,label,value)
  self.field('font_family','フォント','Yu Gothic',['Yu Gothic','Meiryo','MS Gothic','Arial'])
  self.field('color','文字・枠の色（6桁HEX）','333333')
  self.field('border','切り取り用の枠線','あり',['あり','なし'])
  self.field('format','保存形式','PDF',['PDF','PNG','SVG']);self.field('ppi','PNGの解像度（72～200 PPI）','144')
  self.field('preview_page','プレビューのページ','1')
  self.button(self.actions,'印刷前のプレビュー',self.preview).pack(side='left')
  self.button(self.actions,'別名で保存',self.generate).pack(side='left',padx=8)
  self.button(self.actions,'保存先を開く',self.open_output).pack(side='left')
  self.button(self.actions,'出力の詳細…',self.advanced).pack(side='right')
  self.extra={'page_range':tk.StringVar(value=''),'pdf_standard':tk.StringVar(value='1.7'),'tagged':tk.BooleanVar(value=True)}
  self.output.configure(height=3);self.note.set('TypstにはMicrosoft Visual C++ v14 x64ランタイムが必要です。A4縦・複製後400枚/10ページまで。市販シールの品番別位置補正はありません。印刷時は「実際のサイズ／100%」を選び、普通紙で位置を確認してください。印刷はPDF閲覧ソフトから行います。')
  self.status.set('文字と配置を選んでください。初回のみ公式エンジン約22 MBを取得します。')
  self.bind('<Alt-F4>',lambda event:(self.close(),'break')[1])
 def preset(self,c,r):
  if self.busy:return
  self.vars['columns'].set(str(c));self.vars['rows'].set(str(r));self.vars['margin'].set('10');self.vars['gap'].set('3')
 def refresh_fonts(self):
  if self.busy:return
  def done(values):
   for w,_ in self.controls:
    if isinstance(w,ttk.Combobox) and str(w.cget('textvariable'))==str(self.vars['font_family']):w.configure(values=values)
   self.status.set(f'{len(values)}種類のWindowsフォントを選べます。')
  self.start(lambda:core.fonts(self.cancel),done)
 def advanced(self):
  if self.busy:return
  top=tk.Toplevel(self);top.title('出力の詳細');top.geometry('620x250')
  ttk.Label(top,text='保存ページ（空欄＝すべて、例：1,3-5、8-）').pack(anchor='w',padx=12,pady=(12,4))
  w=ttk.Entry(top,textvariable=self.extra['page_range']);w.pack(fill='x',padx=12);self.controls.append((w,'normal'))
  ttk.Label(top,text='PDFの形式（PNG・SVGには使いません）').pack(anchor='w',padx=12,pady=(12,4))
  w=ttk.Combobox(top,textvariable=self.extra['pdf_standard'],values=['1.4','1.7','2.0','a-2b'],state='readonly');w.pack(fill='x',padx=12);self.controls.append((w,'readonly'))
  w=ttk.Checkbutton(top,text='PDFに読み取り順などのタグを付ける',variable=self.extra['tagged']);w.pack(anchor='w',padx=12,pady=12);self.controls.append((w,'normal'))
  ttk.Label(top,text='PDF/A-2bは保存用の形式です。ページを絞ったPDFはタグなしになります。プレビューは保存範囲に関係なく指定ページを表示します。',wraplength=580).pack(anchor='w',padx=12)
  def closed():
   self.controls[:]=[(w,state) for w,state in self.controls if w.winfo_exists() and w.winfo_toplevel()!=top]
   top.destroy()
  top.protocol('WM_DELETE_WINDOW',closed)
 def settings(self):
  values=self.values();options={k:int(values[k]) for k in ['columns','rows','margin','gap','font','repeat']}
  options.update(font_family=values['font_family'],color=values['color'],border=values['border']=='あり')
  if values['border'] not in ['あり','なし']:raise ValueError('枠線を選んでください。')
  items=[[part.strip() for part in line.split('|')] for line in self.input.get('1.0','end-1c').splitlines() if line.strip()]
  core.source(items,**options);return items,options
 def load_text(self):
  if self.busy:return
  name=filedialog.askopenfilename(parent=self,filetypes=[('UTF-8テキスト','*.txt')])
  if not name:return
  try:
   p=safe_path(name)
   if not p.is_file() or p.stat().st_size>128*1024:raise ValueError('128 KiB以内の一覧を選んでください。')
   text=p.read_text(encoding='utf-8-sig')
   if len(text.splitlines())>200:raise ValueError('一覧は200行までです。')
   self.input.delete('1.0','end');self.input.insert('1.0',text)
  except Exception as e:messagebox.showerror('一覧を開けません',str(e),parent=self)
 def preview(self):
  if self.busy:return
  try:items,options=self.settings();page=int(self.vars['preview_page'].get())
  except Exception as e:messagebox.showerror('入力の確認',str(e),parent=self);return
  self.start(lambda:core.render(items,options,self.cancel,preview_page=page),lambda r:(self.picture(r['png']),self.status.set(f"全{r['pages']}ページ中 {page}ページ目の見本です。")))
 def generate(self):
  if self.busy:return
  try:
   items,options=self.settings();fmt={'PDF':'pdf','PNG':'png','SVG':'svg'}[self.vars['format'].get()];ppi=int(self.vars['ppi'].get());extra={k:v.get() for k,v in self.extra.items()}
  except Exception as e:messagebox.showerror('入力の確認',str(e),parent=self);return
  directory=self.choose_save()
  if directory:self.start(lambda:core.render(items,options,self.cancel,folder=directory,fmt=fmt,ppi=ppi,**extra),self.saved)
 def saved(self,result):
  self.last=result['paths'][-1];self.show('\n'.join(Path(p).name for p in result['paths']));self.status.set(f"{result['labels']}枚・{result['pages']}ページを保存しました。")
 def open_output(self):
  if self.last:os.startfile(str(Path(self.last).parent))
 def picture(self,png):
  top=tk.Toplevel(self);top.title('印刷前のプレビュー')
  image=tk.PhotoImage(master=top,data=base64.b64encode(png).decode('ascii'))
  if image.height()>850:image=image.subsample(2,2)
  label=ttk.Label(top,image=image);label.image=image;label.pack(padx=10,pady=10)
  ttk.Label(top,text='画面は縮小表示です。印刷時はPDFを実際のサイズ（100%）で出力してください。').pack(padx=10,pady=(0,10))
 def start(self,job,done):
  if self.busy:return
  self.busy=True;self.cancel.clear()
  for widget,_ in self.controls:widget.configure(state='disabled')
  self.stop.configure(state='normal');self.status.set('処理しています…')
  def work():
   try:self.events.put(('done',(done,job())))
   except Exception as e:self.events.put(('error',str(e)))
  self.worker=threading.Thread(target=work,daemon=False);self.worker.start()
 def destroy(self):
  if self.worker is not None and self.worker.is_alive():self.worker.join(timeout=1)
  for timer in self.tk.call('after','info'):self.after_cancel(timer)
  tk.Tk.destroy(self)

if __name__=='__main__':App().mainloop()
