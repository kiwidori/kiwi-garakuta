"""Convert media and move a short video interval into the GIF editor."""
import tkinter as tk
from tkinter import ttk,messagebox
import bridge,video_ui,gif_ui
from video_options import DEFAULTS

class App(video_ui.App):
 def __init__(self):
  self.gif=None;self.clip=None;self.pending=None;self._busy=False;self.shutting_down=False
  super().__init__();self.title('きうい動画・GIF工房');self.geometry('1160x940');self.minsize(1100,880)
  self.bind('<Alt-F4>',lambda event:(self.close(),'break')[1])
  # Keep the established video controls and expose the connected workflow below.
  panel=ttk.LabelFrame(self,text='動画からGIFへ',padding=8);panel.pack(fill='x',padx=14,pady=(0,10))
  self.gif_fps=tk.StringVar(master=self,value='5')
  ttk.Label(panel,text='取り込みFPS').pack(side='left');ttk.Entry(panel,textvariable=self.gif_fps,width=5).pack(side='left',padx=5)
  self.button(panel,'選択動画の区間をGIFへ',self.send_input).pack(side='left',padx=5)
  self.button(panel,'選択した保存結果の先頭をGIFへ',self.send_result).pack(side='left',padx=5)
  self.button(panel,'画像・GIF・Y4Mを編集',self.open_gif).pack(side='right')
  ttk.Label(self,text='取り込みは10秒・100コマまで。選択動画は「区間・映像」の設定を使用。保存結果は先頭から最大10秒・追加の回転や切り抜きなし。').pack(anchor='w',padx=14,pady=(0,8))
  for widget in self.winfo_children():
   if isinstance(widget,ttk.Frame):
    for child in widget.winfo_children():
     if isinstance(child,ttk.Label) and child.cget('text')=='きうい動画工房':child.configure(text='きうい動画・GIF工房')
 @property
 def busy(self):
  child=self.gif
  return self._busy or self.pending is not None or (child is not None and child.winfo_exists() and (child.worker is not None or child.closing))
 @busy.setter
 def busy(self,value):self._busy=value
 def open_gif(self):
  if self.closing:return None
  if self.gif is not None and self.gif.winfo_exists():
   if self.gif.closing:return None
   self.gif.deiconify();self.gif.lift();return self.gif
  self.gif=gif_ui.App(self);return self.gif
 def send_input(self):
  if self.busy or self.closing:return
  try:
   if not self.paths:raise ValueError('動画を選んでください。')
   path=self.paths[(self.files.curselection() or (0,))[0]];raw=self.settings()
   self.send(path,raw)
  except Exception as exc:messagebox.showerror('GIFへの取り込み',str(exc),parent=self)
 def send_result(self):
  if self.busy or self.closing:return
  try:
   indexes=self.table.selection()
   if len(indexes)!=1:raise ValueError('保存したファイルの一覧から1件を選んでください。')
   path=self.results[self.table.index(indexes[0])]['output'];self.send(path,dict(DEFAULTS))
  except Exception as exc:messagebox.showerror('GIFへの取り込み',str(exc),parent=self)
 def send(self,path,raw):
  if self.gif is not None and self.gif.winfo_exists() and self.gif.paths:
   if not messagebox.askyesno('GIFの入力を置き換える','GIF編集の入力一覧を取り込む動画の画像列に置き換えます。元画像や保存したGIFは削除しません。続けますか？',parent=self):return
  fps=self.gif_fps.get()
  self.job('bridge',lambda:bridge.extract(path,raw,fps,self.cancel))
 def receive_frames(self,clip):
  self.pending=clip;self.after(20,self.accept_frames)
 def accept_frames(self):
  if self.pending is None:return
  if self._busy:self.after(20,self.accept_frames);return
  clip=self.pending
  if self.closing:clip.close();self.pending=None;return
  child=self.open_gif()
  if child is None:self.after(20,self.accept_frames);return
  child.stop_preview();old=self.clip;self.clip=clip
  child.kind.set('画像を並べる');child.paths=list(clip.paths)
  child.vars['fps'].set(str(clip.fps));child.vars['speed'].set('1');child.vars['space'].set('');child.bounce.set(False)
  child.vars['width'].set('0');child.vars['height'].set('0');child.refresh();child.listbox.selection_set(0)
  self.pending=None;child.selected()
  if old:old.close()
  self.status.set(f'{len(clip.paths)}コマをGIF編集へ渡しました。約{clip.duration:.2f}秒。GIF画面で並べ替え・速度・品質を調整して保存できます。')
  child.status.set('動画の区間を取り込みました。FPSで速さを調整してGIFを作れます。')
 def close(self):
  self.closing=True;self.cancel.set();self.status.set('処理を止めて閉じています…')
  if self.gif is not None and self.gif.winfo_exists():self.gif.close()
  if not self.shutting_down:self.shutting_down=True;self.after(30,self.finish_close)
 def destroy(self):
  # Video's queue can request destruction before the GIF queue has drained.
  if not self.closing:self.close()
  elif not self.shutting_down:self.shutting_down=True;self.after(30,self.finish_close)
 def finish_close(self):
  if self.worker is not None and self.worker.is_alive():self.after(30,self.finish_close);return
  if self.gif is not None and self.gif.winfo_exists():self.after(30,self.finish_close);return
  # Drain any successful transfer that arrived while closing; it owns files.
  while not self.events.empty():
   kind,value=self.events.get_nowait()
   if kind=='bridge':value.close()
  if self.pending:self.pending.close();self.pending=None
  if self.clip:self.clip.close();self.clip=None
  self.progress.stop()
  for timer in self.tk.call('after','info'):self.after_cancel(timer)
  tk.Tk.destroy(self)

if __name__=='__main__':App().mainloop()
