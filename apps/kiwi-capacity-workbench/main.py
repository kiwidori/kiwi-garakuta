"""Drive capacity and folder breakdown in one read-only workspace."""
import sys,json,os,queue,threading,tkinter as tk
from pathlib import Path
from tkinter import ttk,messagebox,filedialog
sys.path.insert(0,str(Path(__file__).resolve().parent.parent/'common'))
import disk_view,space_core,runtime,advanced

def safe_folder(value):
    if not isinstance(value,str) or not value or '\x00' in value:raise ValueError('存在するフォルダーを選んでください。')
    path=Path(value).expanduser().absolute()
    if not path.is_dir():raise ValueError('存在するフォルダーを選んでください。')
    if any(p.is_symlink() or p.is_junction() for p in (path,*path.parents)):raise ValueError('リンクやジャンクションは対象に指定できません。')
    return path.resolve()

class App(disk_view.App):
    def __init__(self):
        self.scan_thread=None;self.drive_thread=None;self.scan_cancel=threading.Event();self.drive_cancel=threading.Event()
        self.scan_busy=False;self.drive_busy=False;self.drive_results=queue.Queue()
        self.scanned_root=None;self.pending_root=None;self.last_raw=None;self.last_error=''
        self.drives_rows=[];self.drives_snapshot=[];self.nav_history=[];self.nav_index=-1
        self._closing=False
        super().__init__()
        self.title('きうい容量作業場');self.geometry('1100x880');self.minsize(880,700)
        self.folder.set('C:/Users/Public/Documents')
        first=self.winfo_children()[0]
        panel=ttk.LabelFrame(self,text='ドライブの空き容量',padding=8);panel.pack(fill='x',padx=14,pady=6,before=first)
        columns=('drive','filesystem','total','used','free','usage')
        labels=('ドライブ','形式','総容量','使用量','空き容量','使用率')
        self.drive_tree=ttk.Treeview(panel,columns=columns,show='headings',height=3,selectmode='browse')
        for col,label in zip(columns,labels):
            self.drive_tree.heading(col,text=label,command=lambda c=col:self._sort_drives(c))
            self.drive_tree.column(col,width=120,anchor='w' if col in columns[:2] else 'e')
        self.drive_tree.pack(fill='x')
        row=ttk.Frame(panel);row.pack(fill='x',pady=4)
        for label,callback in [('ドライブ更新',self._refresh_drives),('選択行をコピー',self._copy_drives),('CSV保存',self._save_drives_csv),('選択ドライブを対象に',self._set_target_from_drive)]:ttk.Button(row,text=label,command=callback).pack(side='left',padx=3)
        row=ttk.Frame(self);row.pack(fill='x',padx=14,pady=4,before=first)
        for label,callback in [('選択フォルダーを再解析',self._rescan_selected_folder),('前の対象へ',self._nav_back),('解析結果をJSON保存',self.save_raw)]:ttk.Button(row,text=label,command=callback).pack(side='left',padx=3)
        prefix='profiles/duf/'
        spec=json.loads(Path(runtime.resource_path(prefix+'advanced-spec.json',Path(__file__).parent)).read_text(encoding='utf8'))
        self.duf_controller=advanced.AdvancedController(self,'duf.exe',prefix+'upstream-help.txt',spec,Path(__file__).parent)
        self.advanced_menu.delete(0,'end')
        self.advanced_menu.add_command(label='フォルダー内訳（dust）',command=self.advanced.open_window)
        self.advanced_menu.add_command(label='ドライブ一覧（duf）',command=self.duf_controller.open_window)
        for controller in (self.advanced,self.duf_controller):
            original=controller._run
            controller._run=lambda c=original:c() if not self.busy() else self.status.set('実行中の処理が終わるまでお待ちください。')
        self.protocol('WM_DELETE_WINDOW',self.close)
        self._poll_drives()

    def busy(self):
        if self._closing:return True
        details=(getattr(self,'advanced',None),getattr(self,'duf_controller',None))
        return self.scan_busy or self.drive_busy or any(c and (c.running or (c.worker_thread and c.worker_thread.is_alive())) for c in details)

    def stop_scan(self):
        self.scan_cancel.set();self.drive_cancel.set();self.status.set('停止中…')

    def _update_drive_table(self):
        self.drives_rows=sorted(self.drives_snapshot,key=lambda r:r[getattr(self,'_drive_sort_col','drive')],reverse=getattr(self,'_drive_sort_reverse',False))
        self.drive_tree.delete(*self.drive_tree.get_children());self.drive_tree.tag_configure('high',background='#ffe5e5')
        for i,row in enumerate(self.drives_rows):
            self.drive_tree.insert('','end',iid=str(i),values=(row['drive'],row['filesystem'],space_core.format_size(row['total']),space_core.format_size(row['used']),space_core.format_size(row['free']),f"{row['usage']:.1f}%"),tags=('high',) if row['usage']>=90 else ())

    def _copy_drives(self):
        selected=self.drive_tree.selection()
        if self.busy() or not selected:return
        row=self.drives_rows[int(selected[0])]
        text=f"{row['drive']} {row['filesystem']}\n総容量: {space_core.format_size(row['total'])}\n使用量: {space_core.format_size(row['used'])}\n空き容量: {space_core.format_size(row['free'])}\n使用率: {row['usage']:.1f}%"
        self.clipboard_clear();self.clipboard_append(text);self.status.set('選択行をコピーしました。')

    def _save_drives_csv(self):
        if self.busy() or not self.drives_rows:return
        filename=filedialog.asksaveasfilename(parent=self,defaultextension='.csv',filetypes=[('CSV','*.csv')],confirmoverwrite=True)
        if not filename:return
        try:
            if Path(filename).suffix.lower()!='.csv':raise ValueError('拡張子.csvを指定してください。')
            Path(filename).write_bytes(space_core.csv_bytes(self.drives_rows));self.status.set('CSVを保存しました。')
        except (OSError,ValueError) as e:messagebox.showerror('保存',str(e),parent=self)

    def _set_target_from_drive(self):
        selected=self.drive_tree.selection()
        if self.busy() or not selected:return
        try:self.folder.set(str(safe_folder(self.drives_rows[int(selected[0])]['drive'])))
        except ValueError as e:messagebox.showerror('対象',str(e),parent=self)

    def _rescan_selected_folder(self):
        selected=self.tree.selection()
        if self.busy() or not selected or self.scanned_root is None:return
        try:
            path=safe_folder(str(self.paths[selected[0]]))
            if not path.is_relative_to(self.scanned_root):raise ValueError('解析済みの対象内にあるフォルダーを選んでください。')
            self.folder.set(str(path));self.start_scan()
        except (ValueError,KeyError) as e:messagebox.showerror('対象',str(e),parent=self)

    def _nav_back(self):
        if self.busy() or self.nav_index<=0:return
        self.nav_index-=1;self.folder.set(self.nav_history[self.nav_index]);self.status.set('前の対象を選択しました。「解析」で確認できます。')

    def save_raw(self):
        if self.busy() or self.last_raw is None:return
        filename=filedialog.asksaveasfilename(parent=self,defaultextension='.json',filetypes=[('JSON','*.json')],confirmoverwrite=True)
        if not filename:return
        try:Path(filename).write_bytes(self.last_raw)
        except OSError as e:messagebox.showerror('保存',str(e),parent=self)

    def close(self):
        self._closing=True;self.scan_cancel.set();self.drive_cancel.set()
        controllers=(self.advanced,self.duf_controller)
        for c in controllers:c.cancel_event.set()
        threads=[self.scan_thread,self.drive_thread,*(c.worker_thread for c in controllers)]
        if any(t and t.is_alive() for t in threads):self.after(50,self.close);return
        for timer in self.tk.splitlist(self.tk.call('after','info')):self.after_cancel(timer)
        self.destroy()

    def _sort_drives(self, col):
        if self.busy():return
        if getattr(self, '_drive_sort_col', None) == col:
            self._drive_sort_reverse = not getattr(self, '_drive_sort_reverse', False)
        else:
            self._drive_sort_col = col
            self._drive_sort_reverse = False
        self._update_drive_table()

    def _push_nav(self, path_str):
        if not self.nav_history or self.nav_history[-1] != path_str:
            self.nav_history.append(path_str)
            if len(self.nav_history) > 50:
                self.nav_history.pop(0)
            self.nav_index = len(self.nav_history) - 1

    def start_scan(self):
        if self.busy(): return
        try:folder = safe_folder(self.folder.get())
        except ValueError as e:messagebox.showerror('対象',str(e),parent=self);return
        dust=disk_view.resource_dir()/'dust.exe'
        try: depth = int(self.depth.get())
        except ValueError: depth = 0
        if not folder or not (1 <= depth <= 6) or not Path(dust).exists():
            messagebox.showerror('入力','階層1〜6と同梱dust.exeを確認してください。',parent=self); return
        self.pending_root = folder; self.scan_cancel.clear();self.scan_busy=True;self.status.set("解析中…")
        self.start_button.config(state="disabled"); self.stop_button.config(state="normal")
        self.run_id += 1
        self.scan_thread = threading.Thread(target=self.run_scan, args=(self.run_id, disk_view.command(dust,folder,depth)))
        self.scan_thread.daemon = True; self.scan_thread.start()
        self._push_nav(str(folder))

    def run_scan(self, run_id, args):
        try:
            res = runtime.execute(args[0], args[1:], cancel_event=self.scan_cancel, timeout=300, max_output=1000000)
            if res["returncode"] != 0: self.events.put((run_id, "error", f"rc={res['returncode']}"))
            else:
                parsed = disk_view.parse_result(res["stdout"])
                self.events.put((run_id, "result", parsed, res["stderr"].decode("utf8","replace")[:1000], res["stdout"]))
        except InterruptedError:self.events.put((run_id,'cancelled'))
        except Exception as e: self.events.put((run_id, "error", str(e)))

    def drain_events(self):
        try:
            while True:
                ev = self.events.get_nowait()
                if ev[0] != self.run_id: continue
                if ev[1] == "result":
                    self.scanned_root = self.pending_root; self.last_raw = ev[4]; self.last_error = ev[3]
                    self.tree.delete(*self.tree.get_children());self.paths.clear()
                    self.show_result(ev[2])
                    if ev[3]: self.status.set("一部にアクセスできない可能性があります: " + ev[3][:300])
                elif ev[1] == "error": self.status.set("解析エラー: " + ev[2])
                else: self.status.set("解析を停止しました。")
                self.scan_busy = False; self.start_button.config(state="normal"); self.stop_button.config(state="disabled")
        except queue.Empty: pass
        self.after(80, self.drain_events)

    def _refresh_drives(self):
        if self.busy(): return
        self.drive_busy = True; self.drive_cancel.clear();self.stop_button.config(state="normal")
        self.status.set("ドライブ情報を取得中…")
        self.drive_thread = threading.Thread(target=self._do_refresh_drives)
        self.drive_thread.daemon = True; self.drive_thread.start()

    def _do_refresh_drives(self):
        try:
            res = runtime.execute(str(disk_view.resource_dir()/"duf.exe"), ["--json", "--only", "local"], cancel_event=self.drive_cancel, timeout=15, max_output=1048576)
            if res["returncode"] != 0: self.drive_results.put(("error", f"rc={res['returncode']}"))
            else: self.drive_results.put(("ok", space_core.parse_drives(res["stdout"])))
        except Exception as e: self.drive_results.put(("error", str(e)))

    def _poll_drives(self):
        try:
            while True:
                ev = self.drive_results.get_nowait()
                if ev[0] == "ok":
                    self.drives_rows = ev[1]; self.drives_snapshot = ev[1]
                    self._update_drive_table(); self.status.set("ドライブ情報を更新しました。")
                else: self.status.set("ドライブ取得エラー: " + ev[1])
                self.drive_busy = False;self.stop_button.config(state="disabled")
        except queue.Empty: pass
        self.after(80, self._poll_drives)

if __name__=='__main__':App().mainloop()
