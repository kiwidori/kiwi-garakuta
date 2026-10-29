"""A direct-link download window with optional checksum verification."""
from pathlib import Path
import sys
import tkinter as tk
from tkinter import ttk, messagebox
if not getattr(sys, 'frozen', False):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'common'))
from consumer_ui import Window
from download_core import DownloadEngine, download

ROOT = Path(sys.executable).parent if getattr(sys, 'frozen', False) else Path(__file__).resolve().parent
engine = DownloadEngine(ROOT)


class App(Window):
    def __init__(self):
        super().__init__('きういファイル保存', '資料やZIPなどの直接リンクからまとめて保存。必要ならSHA-256で内容を確認します。', engine)
        ttk.Label(self.form, text='URL（1行に1つ・20件まで）').grid(row=self.row, column=0, sticky='nw', pady=5)
        self.urls = tk.Text(self.form, height=4, width=60, wrap='none', font=('Yu Gothic UI', 10))
        self.urls.grid(row=self.row, column=1, columnspan=2, sticky='ew', pady=5)
        self.controls.append((self.urls, 'normal'))
        self.row += 1
        self.field('folder', '保存先フォルダー', picker='folder')
        self.field('name', '保存名（1件のときのみ・省略可）')
        self.field('sha', 'SHA-256（1件のときのみ・省略可）')
        self.field('transport', '通信', 'HTTPSのみ', ['HTTPSのみ', 'HTTPも許可'])
        self.field('speed', '最大速度', '制限なし', ['制限なし', '1 MiB/秒', '5 MiB/秒', '10 MiB/秒'])
        self.button(self.actions, 'ファイルを保存', self.execute).pack(side='left')
        self.button(self.actions, '結果をコピー', self.copy_results).pack(side='left', padx=10)
        self.result_text = ''
        self.note.set('公開されたファイルの直接リンク向け。各1 GiB・30分まで。途中再開・ログイン・Cookie・プロキシ・動画サイトの解析は非対応です。同名ファイルは別名で保存し、実行・展開はしません。')
        self.status.set('URLと保存先を指定してください。初回のみエンジンの準備が必要です。')
        self.show('PDF・ZIP・画像など、ファイルそのもののURLを入力してください。\nWebページのURLでは、そのページのHTMLが保存される場合があります。\n保存名を省略するとURL末尾の名前を使います。使えない名前はdownload.binになります。')

    def execute(self):
        if self.busy:
            return
        v = self.values()
        v['urls'] = self.urls.get('1.0', 'end-1c')
        from download_core import settings
        try:
            settings(v)
        except (ValueError, OSError) as error:
            messagebox.showinfo('入力を確認してください', str(error), parent=self)
            return
        self.result_text = ''
        def done(results):
            rows = []
            for r in results:
                if r['error']:
                    rows.append(f'取得できませんでした：{r["name"]}\n{r["error"]}')
                else:
                    rows.append(f'保存済み：{r["name"]}（{r["size"]:,} bytes）\n形式：{r["type"]}\nSHA-256：{r["sha256"]}' + ('\n※HTMLです。ファイルの直接リンクか確認してください。' if 'html' in r['type'].lower() else '') + ('\n' + r['warning'] if r.get('warning') else ''))
            self.result_text = '\n\n'.join(rows)
            self.show(self.result_text)
            count = sum(not r['error'] for r in results)
            self.status.set(f'保存 {count}件・失敗 {len(results) - count}件。保存したファイルは自動では開きません。')
        self.start(lambda: download(engine, v, self.cancel, lambda msg: self.events.put(('status', msg))), done)

    def copy_results(self):
        if self.busy or not self.result_text:
            return
        self.clipboard_clear()
        self.clipboard_append(self.result_text)
        self.status.set('結果をコピーしました。')


if __name__ == '__main__':
    App().mainloop()
