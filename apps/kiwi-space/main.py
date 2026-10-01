"""Drive capacity GUI."""
import tkinter as tk
from tkinter import ttk, filedialog
from pathlib import Path
import queue
import threading
from datetime import datetime
from core import read_drives, resource_dir, format_size, csv_bytes


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("きうい空き容量")
        self.geometry("1000x500")
        self.minsize(850, 400)

        self.running = False
        self.rows = []
        self.status = tk.StringVar(value="待機中")

        self.cancel = threading.Event()
        self.results = queue.Queue()
        self.worker = None
        self.sort_key = None
        self.descending = False
        self._build_ui()
        self._poll()

        self.protocol("WM_DELETE_WINDOW", self.close)

    def _build_ui(self):
        main_frame = ttk.Frame(self, padding=8)
        main_frame.pack(fill=tk.BOTH, expand=True)

        top_frame = ttk.Frame(main_frame)
        top_frame.pack(fill=tk.X, pady=(0, 8))

        self.refresh_btn = ttk.Button(top_frame, text="更新", command=self.refresh)
        self.refresh_btn.pack(side=tk.LEFT, padx=(0, 8))

        self.stop_btn = ttk.Button(top_frame, text="停止", command=self.stop, state=tk.DISABLED)
        self.stop_btn.pack(side=tk.LEFT, padx=(0, 8))

        self.copy_btn = ttk.Button(top_frame, text="選択行をコピー", command=self.copy_selected, state=tk.DISABLED)
        self.copy_btn.pack(side=tk.LEFT, padx=(0, 8))

        self.save_btn = ttk.Button(top_frame, text="CSV保存", command=self.save_csv, state=tk.DISABLED)
        self.save_btn.pack(side=tk.LEFT)

        table_frame = ttk.Frame(main_frame)
        table_frame.pack(fill=tk.BOTH, expand=True)
        columns = ('drive', 'filesystem', 'total', 'used', 'free', 'usage')
        self.tree = ttk.Treeview(table_frame, columns=columns, show='headings', selectmode='browse')

        self.tree.heading('drive', text='ドライブ', command=lambda name='drive': self.sort_column(name))
        self.tree.heading('filesystem', text='ファイルシステム', command=lambda name='filesystem': self.sort_column(name))
        self.tree.heading('total', text='総容量', command=lambda name='total': self.sort_column(name))
        self.tree.heading('used', text='使用量', command=lambda name='used': self.sort_column(name))
        self.tree.heading('free', text='空き容量', command=lambda name='free': self.sort_column(name))
        self.tree.heading('usage', text='使用率(%)', command=lambda name='usage': self.sort_column(name))

        self.tree.column('drive', width=80, anchor=tk.CENTER)
        self.tree.column('filesystem', width=120, anchor=tk.CENTER)
        self.tree.column('total', width=120, anchor=tk.E)
        self.tree.column('used', width=120, anchor=tk.E)
        self.tree.column('free', width=120, anchor=tk.E)
        self.tree.column('usage', width=100, anchor=tk.E)

        scrollbar = ttk.Scrollbar(table_frame, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)

        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        bottom_frame = ttk.Frame(main_frame)
        bottom_frame.pack(fill=tk.X, pady=(8, 0))

        status_label = ttk.Label(bottom_frame, textvariable=self.status, anchor=tk.W)
        status_label.pack(side=tk.LEFT, fill=tk.X, expand=True)

        footer_frame = ttk.Frame(self)
        footer_frame.pack(fill=tk.X, side=tk.BOTTOM, pady=(4, 0))
        footer_label = ttk.Label(
            footer_frame,
            text="dufがローカルと分類したドライブを手動更新で表示します。ファイルの走査・削除は行いません。",
            anchor=tk.W
        )
        footer_label.pack(fill=tk.X)

    def _render(self):
        self.tree.delete(*self.tree.get_children())
        self.tree.tag_configure('high', background='#ffe5e5')
        for index, row in enumerate(self.rows):
            values=(row['drive'],row['filesystem'],format_size(row['total']),format_size(row['used']),format_size(row['free']),f"{row['usage']:.1f}%")
            self.tree.insert('', 'end', iid=str(index), values=values, tags=('high',) if row['usage']>=90 else ())

    def refresh(self):
        if self.running:
            return
        self.running=True
        self.rows=[]
        self._render()
        self.cancel.clear()
        self.refresh_btn.config(state='disabled')
        self.stop_btn.config(state='normal')
        self.copy_btn.config(state='disabled')
        self.save_btn.config(state='disabled')
        self.status.set('容量を取得中...')
        self.worker=threading.Thread(target=self._read_worker,daemon=True)
        self.worker.start()

    def _read_worker(self):
        try:
            rows=read_drives(resource_dir()/'duf.exe',self.cancel)
            self.results.put(('ok',rows))
        except InterruptedError:
            self.results.put(('error','停止しました'))
        except TimeoutError:
            self.results.put(('error','15秒以内に取得できませんでした。'))
        except ValueError as exc:
            self.results.put(('error',str(exc)))
        except Exception:
            self.results.put(('error','容量を取得できませんでした。ドライブの接続状態を確認してください。'))

    def _poll(self):
        try:
            while True:
                kind,data=self.results.get_nowait()
                self.running=False
                self.refresh_btn.config(state='normal')
                self.stop_btn.config(state='disabled')
                if kind=='ok':
                    self.rows=data
                    if self.sort_key:
                        self.rows.sort(key=lambda row:row[self.sort_key],reverse=self.descending)
                    self._render()
                    self.copy_btn.config(state='normal')
                    self.save_btn.config(state='normal')
                    self.status.set(f"取得完了 {datetime.now():%H:%M:%S}（手動更新）")
                else:
                    self.status.set(data)
        except queue.Empty:
            pass
        self.after(100,self._poll)

    def stop(self):
        if self.running:
            self.cancel.set()
            self.status.set('停止中...')

    def sort_column(self,name):
        if self.running or not self.rows or name not in ('drive','filesystem','total','used','free','usage'):
            return
        self.descending=not self.descending if self.sort_key==name else False
        self.sort_key=name
        self.rows.sort(key=lambda row:row[name],reverse=self.descending)
        self._render()

    def copy_selected(self):
        selected=self.tree.selection()
        if self.running or not selected:
            return
        row=self.rows[int(selected[0])]
        text=f"{row['drive']}  {row['filesystem']}\n総容量: {format_size(row['total'])}\n使用量: {format_size(row['used'])}\n空き容量: {format_size(row['free'])}\n使用率: {row['usage']:.1f}%"
        self.clipboard_clear()
        self.clipboard_append(text)
        self.status.set('選択行をコピーしました')

    def save_csv(self):
        if self.running or not self.rows:
            return
        filename=filedialog.asksaveasfilename(parent=self,title='容量一覧をCSV保存',defaultextension='.csv',filetypes=[('CSV','*.csv')],initialfile='drive-capacity.csv',confirmoverwrite=True)
        if not filename:
            return
        if Path(filename).suffix.lower()!='.csv':
            self.status.set('拡張子が.csvの保存先を指定してください。')
            return
        try:
            Path(filename).write_bytes(csv_bytes(self.rows))
            self.status.set('CSVを保存しました（容量はバイト単位）')
        except OSError:
            self.status.set('CSVを保存できませんでした。保存先やアクセス権を確認してください。')

    def close(self):
        self.cancel.set()
        if self.worker and self.worker.is_alive():
            self.worker.join(timeout=2)
        self.destroy()

if __name__=='__main__':
    App().mainloop()
