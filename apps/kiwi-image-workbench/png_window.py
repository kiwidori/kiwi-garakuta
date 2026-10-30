"""A same-process PNG window with a shared worker exclusion boundary."""
import json,queue,sys,threading
from pathlib import Path
import tkinter as tk
from tkinter import ttk,filedialog,messagebox
if not getattr(sys,'frozen',False) and 'advanced' not in sys.modules:
 sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'common'))
from advanced import AdvancedController
import png_core
import image_engine

def resources():
 return (Path(sys._MEIPASS) if getattr(sys,'frozen',False) else Path(__file__).resolve().parent)/'png'

class Details(AdvancedController):
 def __init__(self,window):
  self.window=window;self.poll_id=None;self.closing=False
  spec=json.loads((resources()/'advanced-spec.json').read_text(encoding='utf8'))
  super().__init__(window,spec['tool'],'png/upstream-help.txt',spec,resources().parent)
 def _resolve_exe(self):return str(resources()/'oxipng.exe')
 def _on_root_close(self):self.window.close()
 def open_window(self):
  if self.window.closing or self.closing:return
  super().open_window()
  self.toplevel.bind('<Alt-F4>',lambda event:(self._on_toplevel_close(),'break')[1])
 def _run(self):
  if self.window.owner.image_busy or self.window.running or self.window.closing or self.closing or not self.window.events.empty():return
  if self.worker_thread is not None and self.worker_thread.is_alive():return
  super()._run()
 def _poll_queue(self):
  self.poll_id=None
  if not self.toplevel or not self.toplevel.winfo_exists():return
  try:
   while True:
    kind,value=self.result_queue.get_nowait()
    if kind=='done':self.running=False;self.run_btn.configure(state='normal')
    elif not self.closing:
     if kind=='result':self._show_result(value)
     elif kind=='error':self._show_error(value)
  except queue.Empty:pass
  self.poll_id=self.app.after(100,self._poll_queue)
 def _on_toplevel_close(self):
  self.closing=True;self.cancel_event.set()
  if self.worker_thread is not None and self.worker_thread.is_alive():
   self.app.after(30,self._on_toplevel_close);return
  if self.poll_id is not None:self.app.after_cancel(self.poll_id);self.poll_id=None
  super()._on_toplevel_close();self.closing=False

class PNGWindow(tk.Toplevel):
 def __init__(self,owner):
  super().__init__(owner);self.owner=owner;self.title('PNG圧縮 — きうい画像・PNG工房');self.geometry('960x480');self.minsize(850,450)
  self.source=tk.StringVar(master=self);self.destination=tk.StringVar(master=self);self.level=tk.IntVar(master=self,value=2)
  self.status=tk.StringVar(master=self,value='20 MiB・1600万画素までのPNG。APNGには対応していません。')
  self.result=tk.StringVar(master=self);self.running=False;self.closing=False;self.worker=None
  self.cancel=threading.Event();self.events=queue.Queue();self.completed=None;self.poll_id=None
  frame=ttk.Frame(self,padding=14);frame.pack(fill='both',expand=True);frame.columnconfigure(1,weight=1)
  for row,label,var,command in [(0,'元のPNG',self.source,self.pick_source),(1,'保存先PNG',self.destination,self.pick_destination)]:
   ttk.Label(frame,text=label).grid(row=row,column=0,sticky='w',pady=5)
   ttk.Entry(frame,textvariable=var).grid(row=row,column=1,sticky='ew',padx=8)
   ttk.Button(frame,text='選択…',command=command).grid(row=row,column=2)
  ttk.Label(frame,text='圧縮レベル').grid(row=2,column=0,sticky='w',pady=8)
  ttk.Combobox(frame,textvariable=self.level,values=[0,1,2,3,4],state='readonly',width=5).grid(row=2,column=1,sticky='w',padx=8)
  bar=ttk.Frame(frame);bar.grid(row=3,column=0,columnspan=3,sticky='ew',pady=10)
  ttk.Button(bar,text='別名で圧縮',command=self.start).pack(side='left')
  ttk.Button(bar,text='停止',command=self.cancel.set).pack(side='left',padx=8)
  ttk.Button(bar,text='圧縮結果を画像の編集対象へ',command=self.return_result).pack(side='left')
  ttk.Label(frame,textvariable=self.status,wraplength=880).grid(row=4,column=0,columnspan=3,sticky='w',pady=8)
  ttk.Label(frame,textvariable=self.result,wraplength=880).grid(row=5,column=0,columnspan=3,sticky='w',pady=8)
  ttk.Label(frame,text='小さくならない場合は元のバイト列を別名保存します。元画像は変更しません。\n詳細機能では直接CLIオプションを選べます。--alphaは透明部分のRGBを変更します。',wraplength=880).grid(row=6,column=0,columnspan=3,sticky='w',pady=10)
  self.details=Details(self)
  self.traces=[(v,v.trace_add('write',self.invalidate)) for v in (self.source,self.destination)]
  self.protocol('WM_DELETE_WINDOW',self.close);self.bind('<Alt-F4>',lambda event:(self.close(),'break')[1]);self.poll_id=self.after(70,self.poll)
 @property
 def busy(self):
  d=self.details
  return self.running or self.closing or (self.worker is not None and self.worker.is_alive()) or not self.events.empty() or d.running or d.closing or (d.worker_thread is not None and d.worker_thread.is_alive()) or not d.result_queue.empty()
 def invalidate(self,*args):self.completed=None;self.result.set('')
 def set_source(self,path):
  if self.owner.busy:return
  self.source.set(str(path));self.destination.set(str(path.with_name(path.stem+'-optimized.png')))
  self.status.set('PNGを受け取りました。圧縮して新しいファイルに保存できます。')
 def pick_source(self):
  if self.owner.busy:return
  value=filedialog.askopenfilename(parent=self,filetypes=[('PNG','*.png')])
  if value:self.set_source(Path(value))
 def pick_destination(self):
  if self.owner.busy:return
  current=Path(self.destination.get()) if self.destination.get() else None
  value=filedialog.asksaveasfilename(parent=self,defaultextension='.png',filetypes=[('PNG','*.png')],initialdir=str(current.parent) if current else None,initialfile=current.name if current else None)
  if value:self.destination.set(value)
 def start(self):
  if self.owner.busy or self.owner.closing:return
  try:
   src=image_engine.safe_path(self.source.get());dst=image_engine.safe_path(self.destination.get());level=self.level.get()
   if not self.source.get() or not self.destination.get():raise ValueError('元画像と保存先を指定してください。')
   if dst.exists():raise ValueError('既存ファイルは上書きできません。')
  except Exception as exc:self.status.set(str(exc));return
  snapshot=(self.source.get(),self.destination.get());self.completed=None;self.result.set('');self.cancel.clear();self.running=True;self.status.set('圧縮しています…')
  def work():
   try:self.events.put(('ok',(png_core.optimize(resources()/'oxipng.exe',src,dst,level,self.cancel),snapshot,str(dst))))
   except InterruptedError:self.events.put(('error','停止しました。保存済みのファイルは残ります。'))
   except Exception as exc:self.events.put(('error',str(exc)))
   finally:self.events.put(('done',None))
  self.worker=threading.Thread(target=work,daemon=False);self.worker.start()
 def poll(self):
  self.poll_id=None
  try:
   while True:
    kind,value=self.events.get_nowait()
    if kind=='done':self.running=False
    elif kind=='error':self.status.set(value[:300])
    elif kind=='ok':
     result,snapshot,path=value
     if snapshot==(self.source.get(),self.destination.get()) and not self.closing:
      self.completed=path;self.result.set(f"元: {result['before']:,} バイト → 保存: {result['after']:,} バイト（{result['saved_percent']:.2f}%削減）")
      self.status.set('保存しました。圧縮結果を次の画像編集へ渡せます。')
     else:self.status.set('保存しました。入力欄が変更されたため、結果の移送は解除しました。')
  except queue.Empty:pass
  if not self.closing:self.poll_id=self.after(70,self.poll)
 def return_result(self):
  if self.owner.busy or not self.completed:return
  try:self.owner.receive_png(self.completed)
  except Exception as exc:messagebox.showerror('画像編集への取り込み',str(exc),parent=self)
 def close(self):
  if self.closing:return
  self.closing=True;self.cancel.set();self.details._on_toplevel_close();self.after(30,self.finish_close)
 def finish_close(self):
  if self.worker is not None and self.worker.is_alive():self.after(30,self.finish_close);return
  if self.details.worker_thread is not None and self.details.worker_thread.is_alive():self.after(30,self.finish_close);return
  if self.details.toplevel is not None:self.after(30,self.finish_close);return
  if self.poll_id is not None:self.after_cancel(self.poll_id);self.poll_id=None
  for var,token in self.traces:var.trace_remove('write',token)
  while not self.events.empty():self.events.get_nowait()
  self.destroy()
