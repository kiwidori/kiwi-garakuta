"""Same-process duplicate inspection linked to the capacity target."""
import csv
import gc
from pathlib import Path
import queue
import sys
import tempfile
import threading
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from consumer_ui import Window
from consumer_runtime import save_file, safe_path
from duplicate_core import DuplicateEngine, search, root

ROOT = Path(sys.executable).parent if getattr(sys, 'frozen', False) else Path(__file__).resolve().parent


class DuplicateDialog(tk.Toplevel):
    button = Window.button
    field = Window.field
    values = Window.values
    show = Window.show
    choose_save = Window.choose_save

    def __init__(self, owner):
        super().__init__(owner)
        self.owner = owner
        self.title('重複チェック — きういPC作業場')
        self.geometry('1100x970')
        self.minsize(960, 840)
        self.engine = DuplicateEngine(ROOT / 'duplicate-engine')
        self.cancel = threading.Event()
        self.events = queue.Queue()
        self.busy = False
        self.closing = False
        self.worker = None
        self.controls = []
        self.vars = {}
        self.row = 0
        self.report = None
        self.epoch = 0
        self.active_epoch = 0
        self.traces = []
        self.result_paths = {}
        self.body = ttk.Frame(self, padding=16)
        self.body.pack(fill='both', expand=True)
        ttk.Label(self.body, text='フォルダーの重複チェック', font=('Yu Gothic UI', 20, 'bold')).pack(anchor='w')
        ttk.Label(self.body, text='容量確認と同じ対象を使います。元ファイルは変更しません。').pack(anchor='w', pady=8)
        self.button(self.body, '重複エンジンを準備（初回のみ・公式配布を取得）', self.setup).pack(anchor='w')
        self.form = ttk.Frame(self.body)
        self.form.pack(fill='x', pady=8)
        self.form.columnconfigure(1, weight=1)
        self.vars['folder'] = owner.folder
        ttk.Label(self.form, text='容量確認と共通の対象').grid(row=0, column=0, sticky='w', pady=5, padx=(0, 15))
        entry = ttk.Entry(self.form, textvariable=owner.folder)
        entry.grid(row=0, column=1, sticky='ew', pady=5)
        self.controls.append((entry, 'normal'))
        self.button(self.form, '選ぶ…', self.pick_shared).grid(row=0, column=2, padx=(8, 0))
        self.row = 1
        self.field('other', '追加の対象（省略可）', picker='folder')
        self.field('mode', '検索するもの', '重複ファイル', ['重複ファイル', '1つだけのファイル'])
        self.field('depth', 'サブフォルダー', 'すべて', ['すべて', '直下だけ', '2階層まで', '3階層まで'])
        self.field('min', '最小サイズ（KiB）', '0')
        self.field('max', '最大サイズ（MiB）', '512')
        self.field('copies', '重複の最低件数', '2', [str(i) for i in range(2, 11)])
        self.actions = ttk.Frame(self.body)
        self.actions.pack(fill='x', pady=8)
        self.button(self.actions, 'ファイルを調べる', self.search).pack(side='left')
        self.button(self.actions, '結果をCSV保存', self.save).pack(side='left', padx=8)
        self.button(self.actions, '選択ファイルのフォルダーを容量確認へ', self.send_folder).pack(side='left')
        table = ttk.Frame(self.body)
        table.pack(fill='both', expand=True)
        self.tree = ttk.Treeview(table, columns=('group', 'scope', 'path', 'size'), show='headings', selectmode='browse', height=8)
        for key, label, width in [('group', 'グループ', 70), ('scope', '対象', 50), ('path', '相対パス', 650), ('size', 'バイト数', 110)]:
            self.tree.heading(key, text=label)
            self.tree.column(key, width=width, anchor='e' if key == 'size' else 'w')
        scroll = ttk.Scrollbar(table, orient='vertical', command=self.tree.yview)
        self.tree.configure(yscrollcommand=scroll.set)
        self.tree.pack(side='left', fill='both', expand=True)
        scroll.pack(side='right', fill='y')
        self.output = tk.Text(self.body, height=4, wrap='word', state='disabled', font=('Yu Gothic UI', 10))
        self.output.pack(fill='x', pady=8)
        bottom = ttk.Frame(self.body)
        bottom.pack(fill='x')
        self.stop = ttk.Button(bottom, text='停止', command=self.cancel.set, state='disabled')
        self.stop.pack(side='left')
        self.status = tk.StringVar(value='共通の対象を確認し、「ファイルを調べる」を押してください。')
        ttk.Label(bottom, textvariable=self.status, wraplength=900).pack(side='left', padx=8)
        ttk.Label(self.body, text='読み取り専用。対象10,000件（フォルダー含む）・検索ファイル各512 MiB・合計8 GiB・10分まで。リンクなどは除外します。似た写真の判定や削除は行いません。', wraplength=1030).pack(anchor='w', pady=8)
        for v in self.vars.values():
            self.traces.append((v, v.trace_add('write', self.invalidate)))
        self.protocol('WM_DELETE_WINDOW', self.close)
        self.poll_id = self.after(70, self.poll)

    def pick_shared(self):
        if self.owner.busy():
            return
        selected = filedialog.askdirectory(parent=self)
        if selected:
            self.owner.folder.set(selected)

    def setup(self):
        self.start(lambda: self.engine.install(self.cancel, lambda msg: self.events.put(('status', msg))),
                   lambda result: self.status.set('重複エンジンの準備ができました。検索はPC内で行います。'))

    def invalidate(self, *_):
        self.epoch += 1
        self.report = None
        self.result_paths.clear()
        self.tree.delete(*self.tree.get_children())
        self.show('入力が変わりました。「ファイルを調べる」で確認してください。')
        if self.busy:
            self.cancel.set()

    def start(self, job, done):
        if self.owner.busy():
            self.status.set('処理が終わるまでお待ちください。')
            return
        gc.collect()
        self.active_epoch = self.epoch
        self.busy = True
        self.cancel.clear()
        for widget, _ in self.controls:
            widget.configure(state='disabled')
        self.stop.configure(state='normal')
        self.status.set('処理しています…')
        def worker():
            try:
                self.events.put(('done', (done, job())))
            except Exception as error:
                self.events.put(('error', str(error)))
        self.worker = threading.Thread(target=worker, daemon=True)
        self.worker.start()

    def poll(self):
        try:
            while True:
                kind, value = self.events.get_nowait()
                if kind == 'status':
                    self.status.set(value)
                    continue
                self.busy = False
                for widget, state in self.controls:
                    widget.configure(state=state)
                self.stop.configure(state='disabled')
                if self.closing:
                    if self.worker and self.worker.is_alive():
                        self.poll_id = self.after(50, self.poll)
                    else:
                        self.destroy()
                    return
                if self.epoch != self.active_epoch:
                    self.report = None
                    self.status.set('入力が変わったため結果を破棄しました。もう一度検索してください。')
                    continue
                if kind == 'error':
                    self.status.set(value[:300])
                    messagebox.showerror('処理できませんでした', value[:2500], parent=self)
                else:
                    done, result = value
                    try:
                        done(result)
                    except Exception as error:
                        self.status.set(str(error))
                        messagebox.showerror('結果を表示できませんでした', str(error), parent=self)
        except queue.Empty:
            pass
        if self.closing and not self.busy and not (self.worker and self.worker.is_alive()):
            self.destroy()
            return
        self.poll_id = self.after(70, self.poll)

    def search(self):
        if self.owner.busy():
            return
        v = self.values()
        self.invalidate()
        def done(result):
            self.report = result
            for i, group in enumerate(result['groups'], 1):
                for row in group['files']:
                    key = str(len(self.result_paths))
                    self.result_paths[key] = row['path']
                    self.tree.insert('', 'end', iid=key, values=(i, row['scope'], row['relative'], group['size']))
            self.show(f'検索 {result["scanned"]:,}件・条件外などの除外 {result["skipped"]:,}件\n{len(result["groups"]):,}グループ。重複分のサイズ（目安）：{result["extra"] / 1024**2:.2f} MiB\n「1つだけ」は指定した対象・条件内の結果です。ファイルは変更していません。')
            self.status.set('検索結果は検索時点の状態です。全件をCSVへ保存できます。')
        self.start(lambda: search(self.engine, v, self.cancel, lambda msg: self.events.put(('status', msg))), done)

    def save(self):
        if self.owner.busy() or self.report is None:
            return
        folder = self.choose_save()
        if not folder:
            return
        groups = self.report['groups']
        def job():
            with tempfile.TemporaryDirectory(prefix='kiwi-pc-duplicates-csv-') as td:
                source = Path(td) / 'report.csv'
                with source.open('w', encoding='utf-8-sig', newline='') as f:
                    w = csv.writer(f)
                    w.writerow(['グループ', '各ファイルのバイト数', 'SHA-256', '対象', '相対パス'])
                    for i, g in enumerate(groups, 1):
                        for row in g['files']:
                            name = row['relative']
                            w.writerow([i, g['size'], g['sha256'], row['scope'], "'" + name if name.startswith(('=', '+', '-', '@')) else name])
                return save_file(source, folder, '重複チェック', '.csv', self.cancel)
        self.start(job, lambda p: self.status.set('保存しました：' + str(p)))

    def send_folder(self):
        if self.owner.busy() or self.report is None:
            return
        selected = self.tree.selection()
        if not selected:
            self.status.set('ファイルの行を選んでください。')
            return
        try:
            path = safe_path(self.result_paths[selected[0]])
            if not path.is_file():
                raise ValueError('ファイルが見つかりません。再検索してください。')
            target = root(str(path.parent))
            self.owner.folder.set(str(target))
            self.owner.status.set('重複検索のフォルダーを対象にしました。「解析」で容量を確認できます。')
            self.owner.lift()
        except (ValueError, OSError) as error:
            self.status.set(str(error))

    def close(self):
        self.closing = True
        self.cancel.set()
        if self.busy or self.worker and self.worker.is_alive():
            return
        self.destroy()

    def destroy(self):
        try:
            self.after_cancel(self.poll_id)
        except tk.TclError:
            pass
        for v, token in self.traces:
            v.trace_remove('write', token)
        self.traces.clear()
        if getattr(self.owner, 'duplicate_dialog', None) is self:
            self.owner.duplicate_dialog = None
        super().destroy()
        self.vars.clear()
        self.status = None
        gc.collect()
