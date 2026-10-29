"""Convert everyday documents with Pandoc."""
import json
from pathlib import Path
import sys
import tempfile
import zipfile
if not getattr(sys, 'frozen', False):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'common'))
from consumer_runtime import Engine, stage, save_file
from consumer_ui import Window

ROOT = Path(sys.executable).parent if getattr(sys, 'frozen', False) else Path(__file__).resolve().parent
engine = Engine(ROOT)
FORMATS = {'Word (.docx)': ('docx', '.docx'), 'OpenDocument (.odt)': ('odt', '.odt'),
           '電子書籍 (.epub)': ('epub3', '.epub'), 'Web文書 (.html)': ('html5', '.html'),
           'テキスト (.txt)': ('plain', '.txt'), 'Markdown (.md)': ('gfm', '.md'),
           'リッチテキスト (.rtf)': ('rtf', '.rtf')}
READERS = {'.md': 'markdown-raw_html-raw_tex', '.markdown': 'markdown-raw_html-raw_tex',
           '.txt': 'markdown-raw_html-raw_tex', '.html': 'html-raw_html', '.htm': 'html-raw_html',
           '.docx': 'docx', '.odt': 'odt', '.epub': 'epub'}


def convert(v, folder, cancel, preview=False):
    if v['format'] not in FORMATS:
        raise ValueError('保存形式を選んでください。')
    if v['changes'] not in {'変更を反映', '変更前', '変更箇所を残す'}:
        raise ValueError('変更履歴の設定を確認してください。')
    with tempfile.TemporaryDirectory(prefix='kiwi-documents-') as td:
        work = Path(td)
        source = stage(v['input'], work, cancel, READERS, limit=32 * 1024**2)
        if source.suffix in {'.docx', '.odt', '.epub'}:
            with zipfile.ZipFile(source) as archive:
                if len(archive.infolist()) > 5000 or sum(m.file_size for m in archive.infolist()) > 128 * 1024**2:
                    raise ValueError('文書の展開サイズ・ファイル数が上限を超えました。')
        fmt, ext = ('plain', '.txt') if preview else FORMATS[v['format']]
        output = work / ('result' + ext)
        args = ['--sandbox', '--from=' + READERS[source.suffix], '--to=' + fmt,
                '--wrap=none', '--strip-comments', '--standalone', '--output=' + str(output)]
        if v.get('title', '').strip():
            args += ['--metadata=title:' + v['title'][:150]]
        if v.get('toc') == '付ける' and fmt != 'plain':
            args += ['--table-of-contents', '--toc-depth=3']
        if v.get('number') == '付ける' and fmt not in {'plain', 'gfm'}:
            args += ['--number-sections']
        if source.suffix == '.docx':
            args += ['--track-changes=' + {'変更を反映': 'accept', '変更前': 'reject', '変更箇所を残す': 'all'}[v['changes']]]
        args.append(str(source))
        engine.call(args, work, cancel)
        if not output.is_file() or output.stat().st_size > 64 * 1024**2:
            raise ValueError('変換結果を確認できません。')
        if preview:
            return output.read_text(encoding='utf8')[:300000]
        dest = save_file(output, folder, Path(v['input']).stem + '_converted', ext, cancel)
        return str(dest)


class App(Window):
    def __init__(self):
        super().__init__('きうい文書変換', 'Word・電子書籍・Web文書を別の形式へ。本文を確認してから、元の文書を残して保存できます。', engine)
        self.field('input', '変換する文書', picker=[('文書', '*.docx *.odt *.epub *.md *.markdown *.txt *.html *.htm')])
        self.field('format', '保存形式', 'Word (.docx)', list(FORMATS))
        self.field('title', '文書タイトル（省略可）')
        self.field('toc', '目次', '付けない', ['付けない', '付ける'])
        self.field('number', '見出し番号', '付けない', ['付けない', '付ける'])
        self.field('changes', 'Wordの変更履歴', '変更を反映', ['変更を反映', '変更前', '変更箇所を残す'])
        self.button(self.actions, '本文を確認', self.preview).pack(side='left')
        self.button(self.actions, '別形式で保存…', self.save).pack(side='left', padx=10)
        self.note.set('入力32 MiBまで。古いDOC・PDF・暗号化文書・マクロ・外部の画像は非対応です。レイアウトやフォントの完全な再現はできません。')
        self.show('文書を選び、「本文を確認」で内容を確かめられます。\nHTML内のスクリプトやMarkdown内の生HTMLは実行しません。')

    def preview(self):
        v = self.values()
        self.start(lambda: convert(v, None, self.cancel, True), lambda text: (self.show(text), self.status.set('本文を表示しました。')))

    def save(self):
        folder = self.choose_save()
        if folder:
            v = self.values()
            self.start(lambda: convert(v, folder, self.cancel), lambda result: (self.show('保存しました。\n' + result), self.status.set('保存できました。')))


if __name__ == '__main__':
    App().mainloop()
