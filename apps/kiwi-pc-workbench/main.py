"""PC overview, drive capacity and folder breakdown in one workspace."""
import sys,json,queue,threading
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent.parent/'common'))
import capacity,runtime,advanced,disk_view
from pc_panel import PcMixin
safe_folder=capacity.safe_folder

class App(PcMixin,capacity.App):
    def __init__(self):
        self.duplicate_dialog = None
        self.pc_busy=False;self.pc_thread=None;self.pc_cancel=threading.Event();self.pc_results=queue.Queue();self.pc_rows=[]
        source=Path(__file__).resolve().parent
        self.native_paths={e:runtime.resource_path(e+'.exe',source) for e in ('fastfetch','duf','dust')}
        super().__init__()
        self.title('きういPC作業場');self.geometry('1100x980');self.minsize(900,790)
        self.build_pc_panel()
        from tkinter import ttk
        ttk.Label(self.pc_frame,text='通常の概要にはユーザー名・端末名・シリアル番号を表示しません。').pack(anchor='w')
        prefix='profiles/fastfetch/'
        spec=json.loads(Path(runtime.resource_path(prefix+'advanced-spec.json',source)).read_text(encoding='utf8'))
        self.pc_controller=advanced.AdvancedController(self,'fastfetch.exe',prefix+'upstream-help.txt',spec,source)
        self.pc_controller.exe_path=self.native_paths['fastfetch'];original=self.pc_controller._run
        self.pc_controller._run=lambda:original() if not self.busy() else self.status.set('処理が終わるまでお待ちください。')
        self.advanced_menu.delete(0,'end')
        for label,c in [('PC情報（fastfetch）',self.pc_controller),('ドライブ一覧（duf）',self.duf_controller),('フォルダー内訳（dust）',self.advanced)]:self.advanced_menu.add_command(label=label,command=c.open_window)
        self.protocol('WM_DELETE_WINDOW',self.close)
        row=ttk.Frame(self);row.pack(fill='x',padx=14,pady=4,before=self.pc_frame)
        ttk.Button(row,text='現在の対象で重複チェック',command=self.open_duplicates).pack(side='left')
        ttk.Button(row,text='選択フォルダーの重複チェック',command=lambda:self.open_duplicates(True)).pack(side='left',padx=8)

    def open_duplicates(self, selected=False):
        if self.busy():return
        try:
            from duplicate_core import root
            target=self.folder.get()
            if selected:
                items=self.tree.selection()
                if not items:raise ValueError('容量内訳のフォルダーを選んでください。')
                target=str(self.paths[items[0]])
            self.folder.set(str(root(target)))
            if self.duplicate_dialog is None:
                from duplicate_panel import DuplicateDialog
                self.duplicate_dialog=DuplicateDialog(self)
            self.duplicate_dialog.deiconify();self.duplicate_dialog.lift()
        except (ValueError,OSError) as error:self.status.set(str(error))

    def busy(self):
        d=self.duplicate_dialog
        if d and (d.busy or not d.events.empty() or d.worker and d.worker.is_alive()):return True
        c=getattr(self,'pc_controller',None)
        return self.pc_busy or not self.pc_results.empty() or bool(self.pc_thread and self.pc_thread.is_alive()) or super().busy() or not self.events.empty() or not self.drive_results.empty() or any(x and not x.result_queue.empty() for x in (getattr(self,'advanced',None),getattr(self,'duf_controller',None),c)) or bool(c and (c.running or c.worker_thread and c.worker_thread.is_alive()))

    def stop_scan(self):
        if self.duplicate_dialog:self.duplicate_dialog.cancel.set()
        self.pc_cancel.set();super().stop_scan()

    def close(self):
        self._closing=True;self.pc_cancel.set()
        if self.duplicate_dialog:
            self.duplicate_dialog.close()
            if self.duplicate_dialog is not None:self.after(50,self.close);return
        c=getattr(self,'pc_controller',None)
        if c:c.cancel_event.set()
        if self.pc_thread and self.pc_thread.is_alive() or c and c.worker_thread and c.worker_thread.is_alive():self.after(50,self.close);return
        super().close()

if __name__=='__main__':App().mainloop()
