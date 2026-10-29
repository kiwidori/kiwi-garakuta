"""Bounded direct HTTP(S) downloads using a pinned curl build."""
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import time
from urllib.parse import urlsplit, urlunsplit, unquote, quote

from consumer_runtime import Engine, NativeJob, safe_path, check, Cancelled

MAX_FILE = 1024**3
MAX_URLS = 20
SPEEDS = {'制限なし': '0', '1 MiB/秒': '1M', '5 MiB/秒': '5M', '10 MiB/秒': '10M'}


class Deadline:
    def __init__(self, parent):
        self.parent = parent
        self.end = time.monotonic() + 1800

    def is_set(self):
        if time.monotonic() > self.end:
            raise ValueError('1件の処理が30分を超えたため停止しました。')
        return self.parent.is_set()


def filename(value):
    return (bool(value) and len(value) <= 120 and value not in {'.', '..'} and
            not value.endswith((' ', '.')) and not re.search(r'[<>:"/\\|?*\x00-\x1f]', value) and
            not re.fullmatch(r'(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\..*)?', value, re.I))


def url(value, http=False):
    if not value or len(value) > 4096 or any(ord(c) <= 32 or ord(c) == 127 for c in value):
        raise ValueError('URLは空白・改行を含まない4,096文字以内で指定してください。')
    p = urlsplit(value)
    if p.scheme not in ({'http', 'https'} if http else {'https'}) or not p.hostname or p.username is not None or p.password is not None or '\\' in value:
        raise ValueError('ユーザー名・パスワードを含まないHTTPSのURLを指定してください。HTTPは通信設定で許可できます。')
    port = p.port  # Validate the port before invoking curl.
    host = p.hostname.encode('idna').decode('ascii')
    authority = ('[' + host + ']' if ':' in host else host) + ((':' + str(port)) if port is not None else '')
    return urlunsplit((p.scheme, authority, quote(p.path or '/', safe="/%:@!$&'()*+,;=-._~"),
                       quote(p.query, safe="/%?:@!$&'()*+,;=-._~"), ''))


def settings(v):
    raw = [s.strip() for s in v['urls'].splitlines() if s.strip()]
    if not 1 <= len(raw) <= MAX_URLS:
        raise ValueError('URLは1行に1つ、20件まで入力してください。')
    if v['transport'] not in {'HTTPSのみ', 'HTTPも許可'} or v['speed'] not in SPEEDS:
        raise ValueError('通信・速度の設定を選んでください。')
    urls = [url(s, v['transport'] == 'HTTPも許可') for s in raw]
    name, sha = v['name'].strip(), v['sha'].strip().lower()
    if len(urls) > 1 and (name or sha):
        raise ValueError('保存名とSHA-256を指定するときは、URLを1件にしてください。')
    if name and not filename(name):
        raise ValueError('保存名は120文字以内の通常のファイル名を指定してください。')
    if sha and not re.fullmatch('[a-f0-9]{64}', sha):
        raise ValueError('SHA-256は64桁の16進数で入力してください。')
    folder = safe_path(v['folder'], True)
    if not Path(v['folder']).is_absolute() or len(str(folder)) > 110:
        raise ValueError('保存先は110文字以内のローカル絶対パスを選んでください。')
    names = []
    for u in urls:
        suggested = unquote(urlsplit(u).path.rsplit('/', 1)[-1])
        names.append(name or (suggested if filename(suggested) else 'download.bin'))
    return urls, names, folder, sha, SPEEDS[v['speed']]


def sha256(path, cancel):
    h = hashlib.sha256()
    total = 0
    with path.open('rb') as source:
        while chunk := source.read(1024**2):
            check(cancel)
            total += len(chunk)
            if total > MAX_FILE:
                raise ValueError('ファイルが1 GiBを超えました。')
            h.update(chunk)
    return h.hexdigest()


def promote(source, folder, name, cancel):
    p = Path(name)
    for i in range(1000):
        check(cancel)
        safe_path(folder, True)
        dest = safe_path(folder / (p.name if not i else f'{p.stem}_{i}{p.suffix}'))
        try:
            # Both paths are on the same volume. Windows rename never overwrites.
            os.rename(source, dest)
            return dest
        except FileExistsError:
            continue
    raise ValueError('同名のファイルが多すぎます。')


class DownloadEngine(Engine):
    def fetch(self, address, work, cancel, speed, progress, *, limit=MAX_FILE, seconds=1800):
        work = Path(work)
        output = work / 'download.part'
        env = {k: v for k, v in os.environ.items() if not k.upper().startswith('CURL_') and
               k.upper() not in {'HTTP_PROXY', 'HTTPS_PROXY', 'ALL_PROXY', 'NO_PROXY',
                                 'SSL_CERT_FILE', 'SSL_CERT_DIR', 'SSLKEYLOGFILE', 'QLOGDIR'}}
        args = ['--disable', '--globoff', '--silent', '--show-error', '--fail', '--location',
                '--max-redirs', '5', '--proto', '=http,https', '--proto-redir',
                '=https' if address.startswith('https:') else '=http,https',
                '--no-netrc', '--proxy', '', '--noproxy', '*', '--ca-native',
                '--connect-timeout', '20', '--max-time', str(seconds), '--max-filesize', str(limit),
                '--retry', '2', '--retry-delay', '1', '--retry-max-time', '60',
                '--limit-rate', speed, '--output', str(output), '--write-out', '%{json}', '--url', address]
        check(cancel)
        with (work / 'info.json').open('wb') as out, (work / 'error.log').open('wb') as err:
            job = NativeJob()
            try:
                p = subprocess.Popen([str(self.executable()), *args], cwd=work, env=env,
                                     stdin=subprocess.DEVNULL, stdout=out, stderr=err,
                                     creationflags=subprocess.CREATE_NO_WINDOW)
                job.attach(p)
                deadline = time.monotonic() + seconds
                last = 0
                while p.poll() is None:
                    check(cancel)
                    if time.monotonic() > deadline:
                        raise ValueError('1件の処理が30分を超えたため停止しました。')
                    size = output.stat().st_size if output.exists() else 0
                    if size > limit or out.tell() > 1024**2 or err.tell() > 1024**2:
                        raise ValueError('ファイルまたは処理記録が上限を超えました。')
                    if time.monotonic() - last > .5:
                        progress(f'{size / 1024**2:.1f} MiB 取得済み')
                        last = time.monotonic()
                    time.sleep(.08)
            finally:
                job.close()
                if 'p' in locals():
                    p.wait(timeout=10)
        check(cancel)
        if (work / 'info.json').stat().st_size > 1024**2 or (work / 'error.log').stat().st_size > 1024**2:
            raise ValueError('処理記録が上限を超えました。')
        if p.returncode:
            messages = {22: '取得先がエラーを返しました。URLや公開状態を確認してください。',
                        60: '取得先の証明書を確認できませんでした。', 63: 'ファイルが1 GiBの上限を超えています。',
                        28: '通信が時間切れになりました。', 47: '転送先の切り替えが5回を超えました。'}
            # Native error text may include signed URLs. Do not display or retain it.
            raise ValueError(messages.get(p.returncode, f'取得できませんでした（通信エラー {p.returncode}）。'))
        info = json.loads((work / 'info.json').read_bytes())
        if not 200 <= info.get('response_code', 0) < 300 or not output.is_file() or output.stat().st_size > limit:
            raise ValueError('取得したファイルを確認できませんでした。')
        return output, info


def download(engine, v, cancel, progress=lambda msg: None):
    urls, names, folder, expected, speed = settings(v)
    results = []
    saved = []
    try:
        for index, (address, name) in enumerate(zip(urls, names), 1):
            check(cancel)
            bounded = Deadline(cancel)
            success = None
            progress(f'{index}/{len(urls)}件目を取得しています…')
            try:
                if shutil.disk_usage(folder).free < MAX_FILE + 64 * 1024**2:
                    raise ValueError('保存先に1 GiB＋64 MiB以上の空き容量が必要です。')
                with tempfile.TemporaryDirectory(prefix='.kiwi-download-', dir=folder) as td:
                    source, info = engine.fetch(address, Path(td), bounded, speed,
                                                lambda msg: progress(f'{index}/{len(urls)}件目：{msg}'))
                    progress(f'{index}/{len(urls)}件目のSHA-256を確認しています…')
                    digest = sha256(source, bounded)
                    if expected and digest != expected:
                        raise ValueError('SHA-256が指定値と一致しません。ファイルは保存しませんでした。')
                    size = source.stat().st_size
                    dest = promote(source, folder, name, bounded)
                    saved.append(dest.name)
                    success = {'name': dest.name, 'size': size, 'sha256': digest,
                               'type': info.get('content_type') or '不明', 'error': ''}
                results.append(success)
            except Cancelled:
                raise
            except (ValueError, OSError) as error:
                if success:
                    success['warning'] = '保存は完了しましたが、作業ファイルの清掃に失敗しました。'
                    results.append(success)
                else:
                    results.append({'name': name, 'error': str(error)})
        return results
    except Cancelled as error:
        raise Cancelled(f'停止しました。保存済み {len(saved)}件は残しています。\n' + '\n'.join(saved)) from error
