"""Read text from an image, review it, then prepare synthetic speech."""
import multiprocessing
import sys
from pathlib import Path
if not getattr(sys,'frozen',False):sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'common'))

def worker_entry():
 if sys.argv[1:]==['--speech-worker']:
  try:
   from speech_worker import run
   run()
  except Exception:raise SystemExit(2)
  raise SystemExit(0)

if __name__=='__main__':
 multiprocessing.freeze_support()
 worker_entry()

import tkinter as tk
from tkinter import ttk,messagebox
import speech_ui,ocr_ui

class OCRWindow(tk.Toplevel):
 def destroy(self):
  panel=getattr(self,'panel',None)
  if panel is not None and panel.own_busy:
   panel.closing=True;panel.cancel.set();self.after(30,self.destroy);return
  # Cancel only callbacks owned by this toplevel, never the speech root's poll.
  for token in self.tk.call('after','info'):
   script=str(self.tk.call('after','info',token)[0])
   if any(str(command) in script for command in (self._tclCommands or [])):self.after_cancel(token)
  tk.Toplevel.destroy(self)

class OCRPanel(ocr_ui.App):
 def __init__(self,owner,window):
  self.owner=owner;self._busy=False;self.worker=None
  super().__init__(window);window.panel=self
  row=ttk.Frame(window,padding=8);row.pack(fill='x')
  self.button(row,'修正した全文を読み上げへ',lambda:self.send(False)).pack(side='left')
  self.button(row,'選択した文章を読み上げへ',lambda:self.send(True)).pack(side='left',padx=8)
  ttk.Label(row,text='300文字まで。取り込んだあとも修正できます。').pack(side='left')
  window.title('画像の文字を読む — きうい読み取り・読み上げ');window.geometry('1250x920')
  window.bind('<Alt-F4>',lambda event:(self.close(),'break')[1])
 @property
 def own_busy(self):return self._busy or bool(self.worker and self.worker.is_alive()) or not self.events.empty()
 @property
 def busy(self):return self._busy or self.owner.own_busy
 @busy.setter
 def busy(self,value):self._busy=value
 def launch(self,label,fn,done):
  if self.own_busy or self.owner.own_busy or self.closing or self.owner.closing:return
  super().launch(label,fn,done)
 def send(self,selected):
  if self.own_busy or self.owner.own_busy or self.closing or self.owner.closing:return
  try:
   text=self.editor.get('sel.first','sel.last') if selected else self.editor.get('1.0','end-1c')
   self.owner.receive_text(text)
  except tk.TclError:self.status.set('文章欄で送る部分を選択してください。')
  except ValueError as error:self.status.set(str(error))
 def add(self):
  if not self.busy and not self.closing:super().add()
 def add_folder(self):
  if not self.busy and not self.closing:super().add_folder()
 def clear(self):
  if not self.busy and not self.closing:super().clear()
 def read(self,all_images):
  if not self.busy and not self.closing:super().read(all_images)
 def rotate(self):
  if not self.busy and not self.closing:super().rotate()
 def reset_region(self):
  if not self.busy and not self.closing:super().reset_region()
 def close(self):
  self.closing=True;self.cancel.set()
  if not self.own_busy:self.root.destroy()

class App(speech_ui.App):
 def __init__(self):
  self.ocr_window=None;self.ocr=None;self._busy=False;self.shutting_down=False
  super().__init__();self.title('きうい読み取り・読み上げ');self.geometry('1140x1040');self.minsize(1000,960)
  row=ttk.Frame(self.body);row.pack(fill='x',pady=6,before=self.form)
  self.button(row,'画像から文章を読む',self.open_ocr).pack(side='left')
  ttk.Label(row,text='OCR画面で文章を確認・修正し、300文字まで読み上げへ渡せます。').pack(side='left',padx=12)
  self.bind('<Alt-F4>',lambda event:(self.close(),'break')[1])
  for label in self.body.winfo_children():
   if isinstance(label,ttk.Label) and label.cget('text')=='きうい読み上げ':label.configure(text='きうい読み取り・読み上げ')
 @property
 def own_busy(self):return self._busy or bool(getattr(self,'worker',None) and self.worker.is_alive()) or bool(hasattr(self,'events') and not self.events.empty())
 @property
 def busy(self):return self._busy or bool(self.ocr is not None and self.ocr_window is not None and self.ocr_window.winfo_exists() and (self.ocr.own_busy or self.ocr.closing))
 @busy.setter
 def busy(self,value):self._busy=value
 def open_ocr(self):
  if self.closing:return None
  if self.ocr_window is not None and self.ocr_window.winfo_exists():
   if self.ocr.closing:return None
   self.ocr_window.lift();return self.ocr
  self.ocr_window=OCRWindow(self);self.ocr=OCRPanel(self,self.ocr_window);return self.ocr
 def receive_text(self,text):
  if self.own_busy or self.closing or self.ocr is not None and self.ocr.own_busy:return
  if not text.strip():raise ValueError('読み上げへ渡す文章が空です。')
  if len(text)>300:raise ValueError('300文字を超えています。文章欄で読む部分を選び「選択した文章を読み上げへ」を押してください。全文は切り捨てていません。')
  text.encode('utf8')
  if self.input.get('1.0','end-1c').strip() and not messagebox.askyesno('読み上げの本文を置き換える','現在の読み上げ本文を、OCR画面の文章に置き換えます。続けますか？',parent=self.ocr_window):return
  self.stop_audio();self.result=None;self.show('');self.input.delete('1.0','end');self.input.insert('1.0',text)
  self.status.set('OCRの文章を取り込みました。言語・声を確認し、必要なら本文を修正して保存してください。');self.lift()
 def close(self):
  self.closing=True;self.cancel.set();self.stop_audio()
  if self.ocr_window is not None and self.ocr_window.winfo_exists():self.ocr.close()
  if not self.shutting_down:self.shutting_down=True;self.after(30,self.finish_close)
 def destroy(self):self.close()
 def finish_close(self):
  if self.worker is not None and self.worker.is_alive():self.after(30,self.finish_close);return
  if self.ocr_window is not None and self.ocr_window.winfo_exists():self.after(30,self.finish_close);return
  self.stop_audio()
  for timer in self.tk.call('after','info'):self.after_cancel(timer)
  tk.Tk.destroy(self)

if __name__=='__main__':App().mainloop()
