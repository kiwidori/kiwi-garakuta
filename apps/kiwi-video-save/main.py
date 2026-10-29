"""Save a single authorized public video or audio through yt-dlp."""
import json
from pathlib import Path
import sys
import tempfile
from urllib.parse import urlparse
if not getattr(sys, 'frozen', False):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'common'))
from consumer_runtime import Engine, safe_path, save_file
from consumer_ui import Window

ROOT = Path(sys.executable).parent if getattr(sys, 'frozen', False) else Path(__file__).resolve().parent
engine = Engine(ROOT)
BASE = ['--ignore-config', '--no-cache-dir', '--no-playlist', '--no-warnings', '--no-progress',
        '--no-update', '--no-check-formats', '--no-plugin-dirs', '--no-remote-components',
        '--no-js-runtimes', '--no-cookies', '--fixup', 'never', '--socket-timeout', '20',
        '--retries', '1', '--fragment-retries', '1', '--extractor-retries', '1',
        '--playlist-items', '1', '--max-filesize', '256M']


def url(value):
    value = value.strip()
    parsed = urlparse(value)
    if len(value) > 4000 or parsed.scheme not in {'http', 'https'} or not parsed.hostname or parsed.username or parsed.password or any(ord(c) < 32 for c in value):
        raise ValueError('認証情報を含まないhttp(s)のURLを1件入力してください。')
    return value


def selector(v):
    if v['mode'] == '動画（音声付き・結合不要）':
        height = {'元のサイズ': '', '1080pまで': '[height<=?1080]', '720pまで': '[height<=?720]', '480pまで': '[height<=?480]'}.get(v['quality'])
        if height is None:
            raise ValueError('画質を選んでください。')
        return 'best[ext=mp4]' + height + '/best' + height
    if v['mode'] == '音声（配信元の形式）':
        return 'bestaudio/best'
    raise ValueError('保存する種類を選んでください。')


def process(v, folder, cancel, inspect=False):
    address = url(v['url'])
    fmt = selector(v)
    with tempfile.TemporaryDirectory(prefix='kiwi-video-save-') as td:
        work = Path(td)
        args = [*BASE, '--format', fmt, '--dump-single-json', '--skip-download', '--', address]
        raw = engine.call(args, work, cancel, timeout=120, cap=16 * 1024**2)
        data = json.loads(raw)
        if data.get('_type') in {'playlist', 'multi_video'} or data.get('is_live') or data.get('live_status') in {'is_live', 'is_upcoming', 'post_live'}:
            raise ValueError('ライブ配信・プレイリストには対応していません。単独の公開動画を指定してください。')
        if float(data.get('duration') or 0) > 7200:
            raise ValueError('2時間以内の動画・音声を指定してください。')
        extension = str(data.get('ext', '')).lower()
        if extension not in {'mp4', 'webm', 'mkv', 'mov', 'm4a', 'mp3', 'ogg', 'opus', 'wav', 'flac', 'aac'}:
            raise ValueError('対応する動画・音声形式が見つかりません。')
        protocol = str(data.get('protocol', ''))
        if protocol not in {'http', 'https'} or data.get('requested_formats'):
            raise ValueError('直接保存できる単一ファイルがありません。分割配信・映像と音声の結合は非対応です。')
        size = data.get('filesize') or data.get('filesize_approx') or 0
        if size > 256 * 1024**2:
            raise ValueError('256 MiBを超える動画・音声です。')
        info = {'タイトル': str(data.get('title', '動画'))[:300], '形式': extension,
                '長さ（秒）': data.get('duration'), '解像度': data.get('resolution'), 'サイズ（byte・概算含む）': size or '不明'}
        if data.get('height') is None:
            info['画質指定'] = '配信元の高さが不明のため、指定にかかわらず元ファイルを使います。'
        if inspect:
            return info
        # The metadata is fetched again by yt-dlp; only one native HTTP(S) file is accepted.
        filename = 'media.' + extension
        selected_url = url(data['url'])
        # Generic input avoids loading extractor/plugin code a second time and keeps the verified format.
        download = ['--force-generic-extractor', *BASE, '--no-part', '--no-continue', '--no-overwrites',
                    '--output', str(work / filename), '--', selected_url]
        engine.call(download, work, cancel, timeout=900, cap=270 * 1024**2)
        output = work / filename
        if not output.is_file() or not 0 < output.stat().st_size <= 256 * 1024**2:
            raise ValueError('保存結果を確認できません。')
        dest = save_file(output, folder, info['タイトル'], '.' + extension, cancel)
        return str(dest), info


class App(Window):
    def __init__(self):
        super().__init__('きうい動画保存', '自分の動画や、保存が許可された公開動画を1件ずつPCへ。ログイン情報は使いません。', engine)
        self.field('url', '動画のURL')
        self.field('mode', '保存する種類', '動画（音声付き・結合不要）', ['動画（音声付き・結合不要）', '音声（配信元の形式）'])
        self.field('quality', '動画の高さ（不明なら元のサイズ）', '720pまで', ['元のサイズ', '1080pまで', '720pまで', '480pまで'])
        self.button(self.actions, 'タイトル・保存形式を確認', self.inspect).pack(side='left')
        self.button(self.actions, '1件を保存…', self.save).pack(side='left', padx=10)
        self.note.set('単独の公開HTTP(S)ファイル、256 MiB・2時間・15分の処理まで。YouTubeを含む配信サイトは仕様や制限により保存できない場合があります。ログイン・DRM・ライブ・プレイリスト・分割配信・MP3変換は非対応です。')
        self.show('権利者と配信サービスが保存を認めているものに使ってください。\n形式変換は「きうい動画工房」、YouTubeの字幕は「きうい字幕」で行えます。')

    def inspect(self):
        v = self.values()
        self.start(lambda: process(v, None, self.cancel, True), lambda result: (self.show('\n\n'.join(f'{key}：{value if value is not None else "不明"}' for key, value in result.items())), self.status.set('保存できる形式を確認しました。')))

    def save(self):
        folder = self.choose_save()
        if folder:
            v = self.values()
            self.start(lambda: process(v, folder, self.cancel), lambda result: (self.show('保存しました。\n' + result[0]), self.status.set('保存できました。')))


if __name__ == '__main__':
    App().mainloop()
