"""Read-only duplicate and unique file inspection."""
import csv
from pathlib import Path
import sys
import tempfile
if not getattr(sys, 'frozen', False):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'common'))
from consumer_runtime import save_file
from consumer_ui import Window
from duplicate_core import DuplicateEngine, search

ROOT = Path(sys.executable).parent if getattr(sys, 'frozen', False) else Path(__file__).resolve().parent
engine = DuplicateEngine(ROOT)


class App(Window):
    def __init__(self):
        super().__init__('きうい重複チェック', '名前が違っても、内容が同じ写真や書類を見つけます。ファイルは変更しません。', engine)
        self.report = None
        self.field('folder', '対象フォルダー', picker='folder')
        self.field('other', '追加の対象（省略可）', picker='folder')
        self.field('mode', '検索するもの', '重複ファイル', ['重複ファイル', '1つだけのファイル'])
        self.field('depth', 'サブフォルダー', 'すべて', ['すべて', '直下だけ', '2階層まで', '3階層まで'])
        self.field('min', '最小サイズ（KiB）', '0')
        self.field('max', '最大サイズ（MiB）', '512')
        self.field('copies', '重複の最低件数', '2', ['2', '3', '4', '5', '6', '7', '8', '9', '10'])
        for v in self.vars.values():
            v.trace_add('write', lambda *_: self.invalidate())
        self.button(self.actions, 'ファイルを調べる', self.search).pack(side='left')
        self.button(self.actions, '結果をCSV保存', self.save).pack(side='left', padx=10)
        self.note.set('読み取り専用。削除・移動はしません。対象10,000件（フォルダー含む）・検索ファイル各512 MiB・合計8 GiB・10分まで。リンクやクラウド専用ファイルは除外します。似た写真の判定はできません。')
        self.status.set('対象を選んでください。初回のみエンジンの準備が必要です。')
        self.show('ファイル全体の内容が一致するものをグループにまとめます。\n「1つだけのファイル」は、指定した対象と条件の中で一致するものが見つからないファイルです。\n空ファイルも含める場合は最小サイズを0にしてください。')

    def invalidate(self):
        self.report = None

    def search(self):
        v = self.values()
        self.report = None
        def done(result):
            self.report = result
            lines = [f'検索 {result["scanned"]:,}件・条件外などの除外 {result["skipped"]:,}件', f'{len(result["groups"]):,}グループ']
            if not result['unique']:
                lines.append(f'重複分のファイルサイズ（目安）：{result["extra"] / 1024**2:.2f} MiB')
            shown = 0
            for i, group in enumerate(result['groups'], 1):
                if shown >= 500:
                    break
                lines.append(f'\nグループ{i}：各{group["size"]:,} bytes・{len(group["files"])}件')
                for f in group['files']:
                    if shown >= 500:
                        break
                    lines.append(f'  対象{f["scope"]} / {f["relative"]}')
                    shown += 1
            if shown < sum(len(g['files']) for g in result['groups']):
                lines.append('\n画面は先頭500件です。全件はCSVに保存できます。')
            self.show('\n'.join(lines))
            self.status.set(f'{len(result["groups"]):,}グループを確認しました。ファイルは変更していません。')
        self.start(lambda: search(engine, v, self.cancel, lambda msg: self.events.put(('status', msg))), done)

    def save(self):
        if self.busy or self.report is None:
            return
        folder = self.choose_save()
        if not folder:
            return
        groups = self.report['groups']
        def job():
            with tempfile.TemporaryDirectory(prefix='kiwi-duplicate-csv-') as td:
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


if __name__ == '__main__':
    App().mainloop()
