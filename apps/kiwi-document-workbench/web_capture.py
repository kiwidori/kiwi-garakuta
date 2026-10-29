"""Static web snapshots with active content disabled."""
import html
from html.parser import HTMLParser
from pathlib import Path
import sys
import tempfile
from urllib.parse import urlparse
if not getattr(sys, 'frozen', False):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'common'))
from consumer_runtime import Engine, check, save_file

ROOT = Path(sys.executable).parent if getattr(sys, 'frozen', False) else Path(__file__).resolve().parent
engine = Engine(ROOT / 'web-engine')
CSP = "default-src 'none'; img-src data:; style-src 'unsafe-inline' data:; font-src data:; script-src 'none'; object-src 'none'; frame-src 'none'; connect-src 'none'; media-src 'none'; base-uri 'none'; form-action 'none'"
POLICY = '<meta http-equiv="Content-Security-Policy" content="' + html.escape(CSP, quote=True) + '">'


def address(value):
    value = value.strip()
    u = urlparse(value)
    if not 0 < len(value) <= 4000 or u.scheme not in {'http', 'https'} or not u.hostname or u.username or u.password or any(ord(c) < 32 for c in value):
        raise ValueError('認証情報を含まないHTTP(S)のURLを1件入力してください。')
    return value


def signature(v):
    return tuple(v.get(k, '') for k in ['url', 'images', 'styles', 'fonts', 'metadata', 'scope'])


class SnapshotParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=False)
        self.output = []
        self.text = []
        self.title = []
        self.in_title = False
        self.head = False
        self.hidden = 0

    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        if tag == 'base' or tag == 'meta' and str(values.get('http-equiv', '')).strip().lower() == 'refresh':
            return
        if tag == 'head':
            self.head = True
            self.output.append(self.get_starttag_text() + POLICY)
            return
        if tag in {'script', 'style'}:
            self.hidden += 1
        if tag == 'title':
            self.in_title = True
        # Event handlers are discarded even if upstream parsing changes.
        clean = [(k, value) for k, value in attrs if not k.lower().startswith('on')]
        self.output.append('<' + tag + ''.join(' ' + k + ('' if value is None else '="' + html.escape(value, quote=True) + '"') for k, value in clean) + '>')
        if tag in {'p', 'div', 'br', 'li', 'h1', 'h2', 'h3', 'tr'}:
            self.text.append('\n')

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)

    def handle_endtag(self, tag):
        if tag in {'script', 'style'}:
            self.hidden = max(0, self.hidden - 1)
        if tag == 'title':
            self.in_title = False
        if tag != 'base':
            self.output.append('</' + tag + '>')

    def handle_data(self, data):
        self.output.append(data)
        if self.in_title:
            self.title.append(data)
        if not self.hidden:
            self.text.append(data)

    def handle_entityref(self, name):
        self.output.append('&' + name + ';')
        if not self.hidden:
            self.text.append(html.unescape('&' + name + ';'))

    def handle_charref(self, name):
        self.output.append('&#' + name + ';')
        if not self.hidden:
            self.text.append(html.unescape('&#' + name + ';'))

    def handle_decl(self, decl):
        self.output.append('<!' + decl + '>')


def capture(v, cancel):
    url = address(v['url'])
    for key in ['images', 'styles', 'fonts', 'metadata']:
        if v[key] not in {'含める', '省く'}:
            raise ValueError('Web保存の設定を選んでください。')
    if v['scope'] not in {'ページと同じホストだけ', '外部サイトの素材も含める'}:
        raise ValueError('素材の取得範囲を選んでください。')
    with tempfile.TemporaryDirectory(prefix='kiwi-web-capture-') as td:
        work = Path(td)
        output = work / 'page.html'
        args = ['--no-js', '--isolate', '--no-frames', '--no-audio', '--no-video', '--encoding', 'UTF-8',
                '--timeout', '15', '--output', str(output)]
        for key, flag in [('images', '--no-images'), ('styles', '--no-css'), ('fonts', '--no-fonts'), ('metadata', '--no-metadata')]:
            if v[key] == '省く':
                args.append(flag)
        if v['scope'] == 'ページと同じホストだけ':
            args += ['--domain', urlparse(url).hostname]
        args += ['--', url]
        engine.call(args, work, cancel, timeout=180, env={'TEMP': str(work), 'TMP': str(work)})
        check(cancel)
        if not output.is_file() or not 0 < output.stat().st_size <= 32 * 1024**2:
            raise ValueError('Web保存は32 MiBまでです。画像やCSSを省いて再試行してください。')
        parser = SnapshotParser()
        parser.feed(output.read_text(encoding='utf8'))
        parser.close()
        if not parser.head:
            raise ValueError('HTML文書を確認できません。')
        result = ''.join(parser.output).encode('utf8')
        if len(result) > 32 * 1024**2:
            raise ValueError('Web保存が32 MiBを超えました。')
        return {'html': result, 'title': ''.join(parser.title).strip()[:150] or 'Webpage',
                'text': ''.join(parser.text)[:300000], 'signature': signature(v), 'url': url}


def save_snapshot(snapshot, folder, cancel):
    with tempfile.TemporaryDirectory(prefix='kiwi-web-save-') as td:
        path = Path(td) / 'page.html'
        path.write_bytes(snapshot['html'])
        return str(save_file(path, folder, snapshot['title'] + '_saved', '.html', cancel))
