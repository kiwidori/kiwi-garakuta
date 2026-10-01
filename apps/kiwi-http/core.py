"""Bounded xh subprocess requests for the Kiwi HTTP desktop app."""
import os
import sys
import time
import threading
import subprocess
import tempfile
from pathlib import Path
from urllib.parse import urlsplit

MAX_OUTPUT_BYTES = 512 * 1024

def resource_dir():
    return Path(sys._MEIPASS) if getattr(sys, 'frozen', False) else Path(__file__).resolve().parent

def validate_url(url):
    if not isinstance(url, str) or not url or len(url) > 2048:
        raise ValueError('http:// または https:// で始まるURLを2048文字以内で入力してください。')
    if any(c.isspace() or ord(c) < 32 or ord(c) == 127 for c in url):
        raise ValueError('URLに空白や制御文字は使用できません。')
    try:
        parts = urlsplit(url)
        if parts.scheme.lower() not in ('http', 'https') or not parts.hostname or parts.username is not None or parts.password is not None:
            raise ValueError()
        _ = parts.port
        if '\\' in url:
            raise ValueError()
    except ValueError:
        raise ValueError('http/httpsのURLを指定してください。URL内の認証情報は使えません。') from None
    return url

def request(exe: Path, url: str, method: str, cancel: threading.Event):
    url = validate_url(url)
    if method not in ('GET','HEAD'):
        raise ValueError('GET または HEAD を選んでください。')
    if cancel.is_set():
        raise InterruptedError()
    if not exe.is_file():
        raise ValueError('同梱のxh.exeが見つかりません。')
    with tempfile.TemporaryDirectory(prefix='kiwi-http-') as temp:
        folder = Path(temp)
        stdout = folder/'response.bin'
        stderr = folder/'error.bin'
        config = folder/'config'
        config.mkdir()
        env = {k:v for k,v in os.environ.items() if not k.upper().startswith('XH_')}
        env['XH_CONFIG_DIR'] = str(config)
        env['NO_COLOR'] = '1'
        cmd=[str(exe.resolve()), '--ignore-stdin', '--ignore-netrc', '--no-follow', '--no-check-status', '--pretty=none', '--print=hb', '--stream', '--timeout=10', method, url]
        with stdout.open('wb') as out, stderr.open('wb') as err:
            proc=subprocess.Popen(cmd, stdin=subprocess.DEVNULL, stdout=out, stderr=err, cwd=temp, env=env, creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
            try:
                deadline=time.monotonic()+15
                while proc.poll() is None:
                    if cancel.is_set():
                        raise InterruptedError()
                    if time.monotonic()>deadline:
                        raise TimeoutError()
                    if max(stdout.stat().st_size,stderr.stat().st_size)>MAX_OUTPUT_BYTES:
                        raise ValueError('応答が512 KiBを超えたため停止しました。')
                    time.sleep(0.05)
            finally:
                if proc.poll() is None:
                    proc.kill()
                proc.wait()
        if cancel.is_set():
            raise InterruptedError()
        if proc.returncode != 0:
            raise ValueError('送信に失敗しました。URL・接続先・証明書・タイムアウトを確認してください。')
        if stdout.stat().st_size > MAX_OUTPUT_BYTES:
            raise ValueError('応答が512 KiBを超えました。')
        raw=stdout.read_bytes()
        if not raw:
            raise ValueError('応答を取得できませんでした。')
        # Response is displayed as text; it is never executed or rendered as HTML.
        return raw.decode('utf-8',errors='replace')
