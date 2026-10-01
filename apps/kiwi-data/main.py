import sys, json, threading, queue
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'common'))
from runtime import resource_path
from workbench import App, build_args, MAX_IN
from tkinter import ttk, filedialog, messagebox
import tkinter as tk

class DataApp(App):

    def __init__(self, profile, source_dir):
        self.pending_query = ''
        super().__init__(profile, source_dir)

    def _apply_example(self):
        val = self.ex_combo.get()
        if not val:
            return
        self.query_text.delete('1.0', 'end')
        self.query_text.insert('1.0', val.split(': ', 1)[1] if ': ' in val else val)

    def _load_file(self):
        f = filedialog.askopenfilename()
        if not f:
            return
        try:
            p = Path(f)
            size = p.stat().st_size
            if size > MAX_IN:
                messagebox.showerror('読み込みエラー', 'ファイルサイズが2MiBを超えています。')
                return
            with open(p, 'rb') as fh:
                data = fh.read(MAX_IN + 1)
            if len(data) > MAX_IN:
                messagebox.showerror('読み込みエラー', 'ファイルサイズが2MiBを超えています。')
                return
            try:
                text = data.decode('utf-8-sig')
            except UnicodeDecodeError:
                messagebox.showerror('読み込みエラー', '無効なUTF-8エンコーディングです。')
                return
            self.in_text.delete('1.0', 'end')
            self.in_text.insert('1.0', text)
            ext_map = {'.json': 'json', '.yaml': 'yaml', '.yml': 'yaml', '.toml': 'toml', '.xml': 'xml', '.csv': 'csv', '.ini': 'ini', '.hcl': 'hcl', '.kdl': 'kdl', '.ndjson': 'json', '.dasel': 'dasel'}
            if p.suffix.lower() in ext_map:
                self.values['--in'].set(ext_map[p.suffix.lower()])
            self.status_var.set(f'読み込み完了: {p.name}')
        except Exception as e:
            messagebox.showerror('読み込みエラー', f'ファイルを読み込めませんでした: {e}')

    def run(self):
        if self.worker and self.worker.is_alive():
            return
        mode = self.mode_var.get()
        m = next((x for x in self.profile['modes'] if x['label'] == mode), None)
        if not m:
            return
        if not m.get('stdin') and not m.get('files'):
            super().run()
            return
        q_text = self.query_text.get('1.0', 'end-1c')
        if len(q_text.encode('utf-8')) > 64 * 1024:
            messagebox.showerror('エラー', 'クエリが長すぎます (最大64KiB)。')
            return
        self.pending_query = q_text
        super().run()

    def _build_ui(self):
        super()._build_ui()
        self.in_text.master.configure(text='入力データ（UTF-8、2 MiBまで）')
        if hasattr(self, 'path_list') and self.path_list:
            self.path_list.master.pack_forget()
        query_tab = ttk.Frame(self.tabs)
        self.tabs.add(query_tab, text='クエリ')
        ttk.Label(query_tab, text='DSL 式:').pack(anchor='w', padx=5, pady=(5, 0))
        self.query_text = tk.Text(query_tab, width=80, height=4, wrap='none')
        self.query_text.insert('1.0', '$this')
        self.query_text.pack(fill='x', padx=5)
        ex_frame = ttk.Frame(query_tab)
        ex_frame.pack(fill='x', padx=5, pady=5)
        ttk.Label(ex_frame, text='例:').pack(side='left')
        examples = ['変換のみ: $this', '名前を抽出: items.map(name)', '値で絞込み: items.filter(n>1)', '値で並べ替え: items.sortBy(n)', '名前でグループ化: items.groupBy(name)', '値の合計: items.reduce(n,0,$acc+$this)', '指定項目のみ残す: items.map({name:name})', 'タイトルを変更: title="C"', '名前を再帰検索: ..name']
        self.ex_combo = ttk.Combobox(ex_frame, values=examples, state='readonly', width=40)
        self.ex_combo.pack(side='left', padx=5)
        ttk.Button(ex_frame, text='適用', command=self._apply_example).pack(side='left')
        btn_frame = ttk.Frame(query_tab)
        btn_frame.pack(fill='x', padx=5, pady=5)
        ttk.Button(btn_frame, text='UTF8読込', command=self._load_file).pack(side='left', padx=2)
        ttk.Button(btn_frame, text='サンプル入力', command=self._load_demo).pack(side='left', padx=2)
        ttk.Button(btn_frame, text='設定ファイル', command=self._choose_config).pack(side='left', padx=2)
        ttk.Label(query_tab, text='空の式は形式変換のみ。編集後の文書全体を出すときは「入出力」の「編集後の文書全体を返す」を選びます。').pack(anchor='w', padx=5, pady=5)
        self.tabs.select(query_tab)

    def _load_demo(self):
        demo = {'items': [{'name': 'A', 'n': 2}, {'name': 'B', 'n': 1}], 'title': 'kiwi'}
        self.in_text.delete('1.0', 'end')
        self.in_text.insert('1.0', json.dumps(demo, ensure_ascii=False))
        self.values['--in'].set('json')
        if '--out' in self.values:
            self.values['--out'].set('json')

    def _choose_config(self):
        f = filedialog.askopenfilename()
        if f:
            self.values['--config'].set(f)

    def _worker(self, args, stdin_data, mode_def):
        if mode_def.get('stdin'):
            args = ['query', *args, '--', self.pending_query]
        super()._worker(args, stdin_data, mode_def)

def launch():
    source = Path(__file__).resolve().parent
    profile = json.loads(Path(resource_path('profile.json', source)).read_text(encoding='utf-8'))
    app = DataApp(profile, source)
    app.root.mainloop()
    return app
if __name__ == '__main__':
    launch()
