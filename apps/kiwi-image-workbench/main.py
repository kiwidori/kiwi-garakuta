"""Edit images, optimize saved PNGs, and reuse the optimized image."""
import json
import queue
import sys
from pathlib import Path
import tkinter as tk
from tkinter import ttk,messagebox
import image_ui
import image_engine
from png_window import PNGWindow

class App(image_ui.App):
 def __init__(self):
  self.png=None;self._busy=False;self.shutting_down=False
  super().__init__()
  self.title('きうい画像・PNG工房');self.geometry('1140x940');self.minsize(1080,900)
  panel=ttk.LabelFrame(self,text='PNGを小さくする',padding=8);panel.pack(fill='x',padx=14,pady=6)
  self.button(panel,'選択した入力PNGを圧縮へ',self.send_input).pack(side='left',padx=4)
  self.button(panel,'選択した保存結果PNGを圧縮へ',self.send_result).pack(side='left',padx=4)
  self.button(panel,'PNG圧縮を開く',self.open_png).pack(side='right')
  ttk.Label(self,text='JPEGなどは、まず保存形式をPNGにして保存してください。圧縮は別名保存。圧縮結果を次の編集対象へ戻せます。').pack(anchor='w',padx=14,pady=(0,8))
  self.bind('<Alt-F4>',lambda event:(self.close(),'break')[1])
  for frame in self.winfo_children():
   if isinstance(frame,ttk.Frame):
    for label in frame.winfo_children():
     if isinstance(label,ttk.Label) and label.cget('text')=='きうい画像工房':label.configure(text='きうい画像・PNG工房')
 @property
 def busy(self):
  child=self.png
  return self.image_busy or bool(child is not None and child.winfo_exists() and child.busy)
 @property
 def image_busy(self):
  return self._busy or (getattr(self,'worker',None) is not None and self.worker.is_alive()) or (hasattr(self,'events') and not self.events.empty())
 @busy.setter
 def busy(self,value):self._busy=value
 def open_png(self):
  if self.closing:return None
  if self.png is not None and self.png.winfo_exists():
   if self.png.closing:return None
   self.png.lift();return self.png
  self.png=PNGWindow(self);return self.png
 def transfer(self,path):
  if self.busy or self.closing:return
  path=image_engine.safe_path(path)
  if not path.is_file() or path.suffix.lower()!='.png':raise ValueError('PNGを選んでください。他の形式は先にPNGで保存してください。')
  child=self.open_png()
  if child:child.set_source(path)
 def send_input(self):
  if self.busy or self.closing:return
  try:
   if not self.paths:raise ValueError('入力画像を選んでください。')
   self.transfer(self.paths[(self.files.curselection() or (0,))[0]])
  except Exception as exc:messagebox.showerror('PNG圧縮への取り込み',str(exc),parent=self)
 def send_result(self):
  if self.busy or self.closing:return
  try:
   selected=self.table.selection()
   if len(selected)!=1:raise ValueError('保存した画像の一覧から1件を選んでください。')
   self.transfer(self.results[self.table.index(selected[0])]['output'])
  except Exception as exc:messagebox.showerror('PNG圧縮への取り込み',str(exc),parent=self)
 def receive_png(self,path):
  if self.busy or self.closing:return
  path=image_engine.safe_path(path)
  if not path.is_file():raise ValueError('圧縮結果のファイルが見つかりません。')
  if not messagebox.askyesno('次の編集対象へ','入力一覧を圧縮結果の1枚に置き換え、画像加工の設定を初期値に戻します。保存済みの画像は残ります。続けますか？',parent=self.png):return
  self.reset();self.paths=[str(path)];self.files.delete(0,'end');self.files.insert('end',path.name);self.files.selection_set(0)
  self.photos=[];self.original.configure(image='',text='元画像');self.changed.configure(image='',text='変換後のプレビュー')
  self.status.set('圧縮結果を次の編集対象にしました。前回の加工設定はリセットしました。');self.lift()
 def close(self):
  self.closing=True;self.cancel.set();self.status.set('処理を止めて閉じています…')
  if self.png is not None and self.png.winfo_exists():self.png.close()
  if not self.shutting_down:self.shutting_down=True;self.after(30,self.finish_close)
 def destroy(self):
  # An image worker's completion must not destroy a live child worker.
  self.close()
 def finish_close(self):
  if self.worker is not None and self.worker.is_alive():self.after(30,self.finish_close);return
  if self.png is not None and self.png.winfo_exists():self.after(30,self.finish_close);return
  for timer in self.tk.call('after','info'):self.after_cancel(timer)
  tk.Tk.destroy(self)

if __name__=='__main__':App().mainloop()
