"""Folder comparison and copy UI."""
import csv
from pathlib import Path
import sys
import tempfile
if not getattr(sys, 'frozen', False):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'common'))
from consumer_runtime import save_file
from consumer_ui import Window
from tkinter import messagebox
from copy_core import LocalEngine, compare, apply

ROOT = Path(sys.executable).parent if getattr(sys, 'frozen', False) else Path(__file__).resolve().parent
engine = LocalEngine(ROOT)


class App(Window):
    def __init__(self):
        super().__init__('きういフォルダーコピー', 'フォルダーを見比べて、足りないファイルを追加。コピー先のファイルは残します。', engine)
        self.plan = None
        self.field('source', 'コピー元フォルダー', picker='folder')
        self.field('target', 'コピー先フォルダー', picker='folder')
        for v in self.vars.values():
            v.trace_add('write', lambda *_: self.invalidate())
        self.button(self.actions, 'フォルダーを比較', self.compare).pack(side='left')
        self.button(self.actions, '不足分をコピー', self.execute).pack(side='left', padx=10)
        self.button(self.actions, '比較結果をCSV保存', self.save).pack(side='left')
        self.note.set('ローカルドライブ・USB向け。各2,000件（フォルダー含む）・各512 MiB・合計2 GiBまで。空フォルダー、リンク、クラウド専用ファイルは対象外。上書き・削除はしません。停止時は追加済みのファイルが残る場合があります。')
        self.status.set('フォルダーを選んで比較してください。初回だけエンジンの準備が必要です。')
        self.show('同じ名前でも内容が異なるファイルは、変更せず一覧でお知らせします。\n比較・コピーはPC内で処理します。クラウドへの接続設定は使いません。')

    def invalidate(self):
        self.plan = None

    def compare(self):
        v = self.values()
        self.plan = None
        def done(plan):
            self.plan = plan
            rows = plan['rows']
            counts = {s: sum(r['status'] == s for r in rows) for s in sorted({r['status'] for r in rows})}
            self.show('\n'.join(f'{s}：{n}件' for s, n in counts.items()) + '\n\n' + '\n'.join(f'{r["status"]}\t{r["path"]}\t{r["size"]:,} bytes' for r in rows[:500]) + ('\n\n画面は先頭500件です。全件はCSVへ保存できます。' if len(rows) > 500 else ''))
            self.status.set(f'比較しました。追加予定 {counts.get("追加予定", 0)}件。同じ名前のファイルは上書きしません。')
        self.start(lambda: compare(engine, v['source'], v['target'], self.cancel), done)

    def execute(self):
        if self.busy:
            return
        if not self.plan:
            messagebox.showinfo('先に比較してください', '「フォルダーを比較」を押してください。', parent=self)
            return
        plan = self.plan
        count = sum(r['status'] == '追加予定' for r in plan['rows'])
        if not count:
            messagebox.showinfo('追加なし', '不足しているファイルはありません。', parent=self)
            return
        if not messagebox.askyesno('不足分をコピー', f'{count}件をコピー先へ追加しますか？\n既存ファイルは変更しません。', parent=self):
            return
        self.plan = None
        self.start(lambda: apply(engine, plan, self.cancel, lambda msg: self.events.put(('status', msg))),
                   lambda result: (self.show('追加しました。\n' + '\n'.join(result)), self.status.set(f'{len(result)}件を追加しました。最新の状態は再度比較してください。')))

    def save(self):
        if self.busy or not self.plan:
            return
        folder = self.choose_save()
        if not folder:
            return
        rows = self.plan['rows']
        def job():
            with tempfile.TemporaryDirectory(prefix='kiwi-copy-csv-') as td:
                p = Path(td) / 'comparison.csv'
                with p.open('w', encoding='utf-8-sig', newline='') as f:
                    w = csv.writer(f)
                    w.writerow(['状態', '相対パス', 'バイト数'])
                    for r in rows:
                        # Spreadsheet programs must not interpret names as formulas.
                        name = r['path']
                        w.writerow([r['status'], "'" + name if name.startswith(('=', '+', '-', '@', '\t', '\r')) else name, r['size']])
                return save_file(p, folder, 'フォルダー比較', '.csv', self.cancel)
        self.start(job, lambda p: self.status.set('保存しました：' + str(p)))


if __name__ == '__main__':
    App().mainloop()
