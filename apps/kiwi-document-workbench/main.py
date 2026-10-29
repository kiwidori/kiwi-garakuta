"""Read, save and convert documents with a shared web snapshot."""
from pathlib import Path
import sys
import tempfile
if not getattr(sys, 'frozen', False):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'common'))
from consumer_ui import Window
from consumer_runtime import check
from document import engine, FORMATS, convert_local
import web_capture


def process(v, folder, cancel, *, preview=False, html_only=False, cached=None):
    if v['source'] not in {'手元の文書', 'Webページ'}:
        raise ValueError('入力の種類を選んでください。')
    if v['source'] == '手元の文書':
        if html_only:
            raise ValueError('「Webページ」を選んでURLを入力してください。')
        return {'result': convert_local(v, folder, cancel, preview), 'snapshot': None}
    snapshot = cached if cached and cached['signature'] == web_capture.signature(v) else web_capture.capture(v, cancel)
    check(cancel)
    if html_only:
        return {'result': web_capture.save_snapshot(snapshot, folder, cancel), 'snapshot': snapshot}
    if preview:
        return {'result': snapshot['text'], 'snapshot': snapshot}
    with tempfile.TemporaryDirectory(prefix='kiwi-document-web-') as td:
        source = Path(td) / 'Webpage.html'
        source.write_bytes(snapshot['html'])
        options = {**v, 'input': str(source), 'title': v['title'] or snapshot['title']}
        result = convert_local(options, folder, cancel)
        return {'result': result, 'snapshot': snapshot}


class App(Window):
    def __init__(self):
        super().__init__('きうい文書作業場', 'Webページを1つのHTMLに保存し、そのままWordや電子書籍へ。手元の文書も同じ画面で変換できます。', engine)
        self.snapshot = None
        self.geometry('1140x1000')
        self.button(self.body, 'Webエンジンを準備（初回のみ・約5.3 MiB）', self.setup_web).pack(before=self.form, anchor='w', pady=(0, 8))
        self.field('source', '入力の種類', '手元の文書', ['手元の文書', 'Webページ'])
        self.field('input', '手元の文書', picker=[('文書', '*.docx *.odt *.epub *.md *.markdown *.txt *.html *.htm')])
        self.field('url', 'WebページのURL')
        self.field('images', 'Webの画像', '含める', ['含める', '省く'])
        self.field('styles', 'Webの見た目（CSS）', '含める', ['含める', '省く'])
        self.field('fonts', 'Webフォント', '省く', ['含める', '省く'])
        self.field('metadata', '取得元URL・日時の記録', '含める', ['含める', '省く'])
        self.field('scope', '素材の取得範囲', 'ページと同じホストだけ', ['ページと同じホストだけ', '外部サイトの素材も含める'])
        self.field('format', '変換後の形式', 'Word (.docx)', list(FORMATS))
        self.field('title', '文書タイトル（空欄で自動）')
        self.field('toc', '目次', '付けない', ['付けない', '付ける'])
        self.field('number', '見出し番号', '付けない', ['付けない', '付ける'])
        self.field('changes', 'Wordの変更履歴', '変更を反映', ['変更を反映', '変更前', '変更箇所を残す'])
        self.button(self.actions, '本文を確認・取得', self.preview).pack(side='left')
        self.button(self.actions, 'Webを再取得', self.refresh).pack(side='left', padx=6)
        self.button(self.actions, 'WebをHTML保存…', self.save_html).pack(side='left', padx=6)
        self.button(self.actions, '別形式で保存…', self.save).pack(side='left', padx=6)
        self.note.set('Webは静的な公開ページ用。JavaScript・動画・音声・ログインは非対応です。入力／Web保存32 MiBまで。Webの設定を変えなければ、確認した内容を再取得せず使います。')
        self.show('Web保存：URLを取得 → 本文を確認 → HTML保存、またはWord・EPUBなどへ変換。\n手元の文書は、元のファイルを変更せず従来と同じ形式で変換できます。\n取得したページのスクリプトは実行せず、保存後の自動通信も制限します。')

    def setup_web(self):
        self.start(lambda: web_capture.engine.install(self.cancel, lambda msg: self.events.put(('status', msg))),
                   lambda _: self.status.set('Webエンジンを準備しました。'))

    def completed(self, value, preview=False):
        if value['snapshot'] is not None:
            self.snapshot = value['snapshot']
        self.show(value['result'] if preview else '保存しました。\n' + value['result'])
        self.status.set('取得した内容を表示しました。' if preview else '保存できました。')

    def preview(self):
        v, cached = self.values(), self.snapshot
        self.start(lambda: process(v, None, self.cancel, preview=True, cached=cached), lambda result: self.completed(result, True))

    def refresh(self):
        if self.busy:
            return
        self.snapshot = None
        self.vars['source'].set('Webページ')
        self.preview()

    def save_html(self):
        self.export(True)

    def save(self):
        self.export(False)

    def export(self, html_only):
        folder = self.choose_save()
        if folder:
            v, cached = self.values(), self.snapshot
            self.start(lambda: process(v, folder, self.cancel, html_only=html_only, cached=cached), self.completed)


if __name__ == '__main__':
    App().mainloop()
