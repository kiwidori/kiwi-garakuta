"""Mode-limited browser gateway backed by a private qrcp instance."""
import http.client
import ipaddress
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import os
from pathlib import Path
import queue
import re
import secrets
import shutil
import socket
import ssl
import subprocess
import tempfile
import threading
import time
from urllib.parse import quote

from native_job import NativeJob
from upload_gate import MAX_BODY, native_body, parse_upload, verified_files


class Server(ThreadingHTTPServer):
    daemon_threads = False
    block_on_close = True

    def __init__(self, owner):
        self.owner = owner
        self.slots = threading.BoundedSemaphore(4)
        self.sockets = set()
        self.socket_lock = threading.Lock()
        super().__init__((owner.address, owner.requested_port), Handler)
        if owner.tls_context is not None:
            try:
                self.socket = owner.tls_context.wrap_socket(self.socket, server_side=True, do_handshake_on_connect=False)
            except BaseException:
                self.server_close()
                raise

    def handle_error(self, request, address):
        self.owner.emit(('request_failed', '接続が中断されました。'))

    def process_request(self, request, address):
        if not self.slots.acquire(blocking=False):
            self.shutdown_request(request)
            return
        with self.socket_lock:
            self.sockets.add(request)
        try:
            super().process_request(request, address)
        except BaseException:
            with self.socket_lock:
                self.sockets.discard(request)
            self.slots.release()
            raise

    def process_request_thread(self, request, address):
        try:
            super().process_request_thread(request, address)
        finally:
            with self.socket_lock:
                self.sockets.discard(request)
            self.slots.release()

    def stop_clients(self):
        with self.socket_lock:
            sockets = tuple(self.sockets)
        for connection in sockets:
            try:
                connection.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass


class Handler(BaseHTTPRequestHandler):
    server_version = 'KiwiTransfer'
    sys_version = ''
    protocol_version = 'HTTP/1.0'

    def setup(self):
        self.request.settimeout(2)
        if isinstance(self.request, ssl.SSLSocket):
            self.request.do_handshake()
        super().setup()

    def log_message(self, *args):
        pass

    def reply(self, status, text):
        data = text.encode('utf8')
        self.send_response(status)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.send_header('Content-Length', str(len(data)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Referrer-Policy', 'no-referrer')
        self.send_header('Content-Security-Policy', "default-src 'none'; form-action 'self'; frame-ancestors 'none'")
        self.end_headers()
        if self.command != 'HEAD':
            self.wfile.write(data)

    def do_GET(self):
        self.dispatch()

    def do_HEAD(self):
        self.dispatch()

    def do_POST(self):
        self.dispatch()

    def dispatch(self):
        session = self.server.owner
        try:
            if session.cancel.is_set():
                self.reply(410, '共有は終了しました。')
                return
            if self.path != session.route:
                self.reply(404, 'ページが見つかりません。')
                return
            hosts = self.headers.get_all('Host', [])
            origins = self.headers.get_all('Origin', [])
            lengths = self.headers.get_all('Content-Length', [])
            if (hosts != [session.host] or len(origins) > 1
                    or origins and origins != [session.scheme + '://' + session.host]
                    or self.headers.get('Transfer-Encoding') is not None
                    or len(lengths) > 1):
                self.reply(400, '送信先または送信形式が違います。')
                return
            if self.command not in ({'GET', 'HEAD'} if session.mode == 'send' else {'GET', 'HEAD', 'POST'}):
                self.reply(405, 'この操作は使えません。')
                return
            if self.command == 'POST':
                if not lengths or not re.fullmatch(r'[0-9]{1,9}', lengths[0]):
                    self.reply(411, '送信サイズが必要です。')
                    return
                size = int(lengths[0])
                if not 0 < size <= MAX_BODY:
                    self.reply(413, '1回の送信は32 MiB以下です。')
                    return
                if len(self.headers.get_all('Content-Type', [])) != 1:
                    self.reply(400, 'ファイル形式を指定してください。')
                    return
                if not session.transfer_lock.acquire(blocking=False):
                    self.reply(409, '別の転送を処理しています。')
                    return
                try:
                    deadline = time.monotonic() + 30
                    data = bytearray()
                    while len(data) < size:
                        if session.cancel.is_set() or time.monotonic() >= deadline:
                            raise TimeoutError('送信が中断されました。')
                        chunk = self.rfile.read1(min(65536, size - len(data)))
                        if not chunk:
                            raise ValueError('送信が途中で切れました。')
                        data.extend(chunk)
                    files = parse_upload(self.headers['Content-Type'], bytes(data))
                    saved = session.receive(files)
                    try:
                        self.reply(200, '<!doctype html><meta charset="utf-8"><p>受け取りました。このページを閉じてください。</p>')
                    finally:
                        session.emit(('received', str(saved)))
                finally:
                    session.transfer_lock.release()
            elif lengths and lengths != ['0']:
                self.reply(400, 'この操作にデータは送れません。')
            elif session.mode == 'receive':
                self.reply(200, '<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width">'
                           '<h1>きうい転送</h1><p>1回32 MiB・20ファイルまで。送信後はPCで受信を確認してください。</p>'
                           '<form method="post" enctype="multipart/form-data">'
                           '<input type="file" name="files" multiple required><button>PCへ送る</button></form>')
            else:
                self.download(session)
        except (ValueError, UnicodeError) as e:
            self.reply(400, 'ファイルの名前または送信内容を確認してください。')
        except (OSError, TimeoutError, http.client.HTTPException):
            # No path, internal URL, or request token goes into public responses.
            session.emit(('request_failed', '転送が中断されました。もう一度お試しください。'))

    def download(self, session):
        connection = http.client.HTTPConnection('127.0.0.1', session.native_port, timeout=5)
        try:
            headers = {}
            if self.headers.get('Range') is not None:
                ranges = self.headers.get_all('Range')
                if len(ranges) != 1 or not re.fullmatch(r'bytes=(?:[0-9]{1,12}-[0-9]{0,12}|-[0-9]{1,12})', ranges[0]):
                    self.reply(400, 'ファイルの一部取得は1つの範囲で指定してください。')
                    return
                headers['Range'] = ranges[0]
            connection.request(self.command, '/send/' + session.native_token, headers=headers)
            response = connection.getresponse()
            if response.status not in (200, 206, 416):
                raise ValueError('native send failed')
            self.send_response(response.status)
            for key in ('Content-Length', 'Content-Type', 'Content-Range', 'Accept-Ranges', 'Last-Modified'):
                value = response.getheader(key)
                if value is not None:
                    self.send_header(key, value)
            self.send_header('Content-Disposition', "attachment; filename=download; filename*=UTF-8''" + quote(session.send_name, safe=''))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('Referrer-Policy', 'no-referrer')
            self.end_headers()
            transferred = 0
            if self.command != 'HEAD':
                while not session.cancel.is_set():
                    chunk = response.read(65536)
                    if not chunk:
                        break
                    self.wfile.write(chunk)
                    transferred += len(chunk)
                # Range downloads are progress, not proof of complete transfer.
                if response.status == 200 and transferred == session.send_size:
                    session.emit(('sent', transferred))
        finally:
            connection.close()


def bind_address(value):
    ip = ipaddress.IPv4Address(value)
    allowed = ('10.0.0.0/8', '172.16.0.0/12', '192.168.0.0/16', '100.64.0.0/10', '127.0.0.0/8')
    if not any(ip in ipaddress.ip_network(network) for network in allowed):
        raise ValueError('このPCのLAN内のIPv4アドレスを指定してください。')
    return str(ip)


def url_hostname(value, fallback):
    if not value:
        return fallback
    name = value.encode('idna').decode('ascii').lower()
    if (len(name) > 253 or not all(re.fullmatch(r'[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?', label)
                                   for label in name.split('.'))):
        raise ValueError('ホスト名にはポートやURLを含めず、DNS名だけを入力してください。')
    return name


class Session:
    """Explicit start/stop; native stays loopback even with a selected LAN endpoint."""
    def __init__(self, exe, mode, *, source=None, destination=None, lifetime=300, address='127.0.0.1', port=0, cancel=None,
                 hostname='', certificate='', private_key=''):
        if mode not in ('send', 'receive') or not 1 <= lifetime <= 3600:
            raise ValueError('転送の設定が違います。')
        if type(port) is not int or port != 0 and not 1024 <= port <= 65535:
            raise ValueError('ポート番号は0（自動）または1024～65535です。')
        self.address, self.requested_port = bind_address(address), port
        self.url_name = url_hostname(hostname, self.address)
        self.tls_context = None
        self.scheme = 'http'
        if certificate or private_key:
            if not certificate or not private_key:
                raise ValueError('HTTPSには証明書と秘密鍵の両方が必要です。')
            for path in (certificate, private_key):
                if not Path(path).is_file() or Path(path).stat().st_size > 2 * 1024**2:
                    raise ValueError('証明書と秘密鍵は2 MiB以下のPEMファイルを選んでください。')
            context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            context.minimum_version = ssl.TLSVersion.TLSv1_2
            context.load_cert_chain(certificate, private_key, password=lambda: '')
            self.tls_context, self.scheme = context, 'https'
        self.mode, self.exe = mode, Path(exe).resolve()
        if source and (Path(source).is_symlink() or Path(source).is_junction()):
            raise ValueError('リンクは送れません。')
        self.source = Path(source).resolve() if source else None
        self.destination = Path(destination).resolve() if destination else None
        if mode == 'send' and (not self.source or not self.source.is_file()):
            raise ValueError('送るファイルを選んでください。')
        if mode == 'receive' and (not self.destination or not self.destination.is_dir()):
            raise ValueError('受信先フォルダーを選んでください。')
        self.lifetime = lifetime
        self.cancel = cancel if cancel is not None else threading.Event()
        self.events = queue.Queue(maxsize=128)
        self.event_lock = threading.Lock()
        self.transfer_lock = threading.Lock()
        self.stop_lock = threading.Lock()
        self.proc = self.job = self.server = self.server_thread = self.reader = None
        self.work = None
        self.started = False

    def emit(self, value):
        with self.event_lock:
            try:
                self.events.put_nowait(value)
            except queue.Full:
                # Transfer completion must survive a flood of failed requests.
                if value[0] != 'request_failed':
                    try:
                        self.events.get_nowait()
                    except queue.Empty:
                        pass
                    self.events.put_nowait(value)

    def start(self):
        if self.started:
            raise ValueError('共有を再開するには新しい転送を作成してください。')
        self.started = True
        try:
            self.work = tempfile.TemporaryDirectory(prefix='kiwi-browser-transfer-')
            self.root = Path(self.work.name)
            self.output = self.root / 'native-output'
            self.output.mkdir()
            config = self.root / 'config.json'
            config.write_text('{}', encoding='utf8')
            self.native_token = secrets.token_hex(24)
            self.route = '/' + self.mode + '/' + secrets.token_hex(24)
            args = [str(self.exe), '--config', str(config), '--interface', 'any', '--bind', '127.0.0.1',
                    '--path', self.native_token, '--keep-alive', self.mode]
            if self.mode == 'send':
                # Only a snapshot is served, never mutable source or a directory.
                snapshot = self.root / 'send.bin'
                copied = 0
                with self.source.open('rb') as input_file, snapshot.open('xb') as output_file:
                    while chunk := input_file.read(65536):
                        if self.cancel.is_set():
                            raise InterruptedError('停止しました。')
                        copied += len(chunk)
                        if copied > 256 * 1024**2:
                            raise ValueError('送信できるファイルは256 MiBまでです。')
                        output_file.write(chunk)
                self.send_name, self.send_size = self.source.name, snapshot.stat().st_size
                args += [str(snapshot)]
            else:
                args += ['--output', str(self.output)]
            env = {k: v for k, v in os.environ.items() if not k.upper().startswith('QRCP_')}
            self.job = NativeJob()
            self.proc = subprocess.Popen(args, cwd=self.root, env=env, stdin=subprocess.DEVNULL,
                                         stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                         creationflags=subprocess.CREATE_NO_WINDOW)
            self.job.attach(self.proc)
            ready = threading.Event()
            def read_output():
                total = 0
                for line in self.proc.stdout:
                    total += len(line)
                    if total > 1024**2:
                        self.cancel.set()
                        break
                    match = re.search(rb'http://127\.0\.0\.1:([0-9]+)/' + self.mode.encode() + b'/' + self.native_token.encode(), line)
                    if match:
                        self.native_port = int(match[1])
                        ready.set()
            self.reader = threading.Thread(target=read_output, daemon=True)
            self.reader.start()
            end = time.monotonic() + 10
            while not ready.wait(.05):
                if self.cancel.is_set():
                    raise InterruptedError('停止しました。')
                if self.proc.poll() is not None or time.monotonic() >= end:
                    raise RuntimeError('転送用プログラムを開始できませんでした。')
            if self.cancel.is_set():
                raise InterruptedError('停止しました。')
            self.server = Server(self)
            self.port = self.server.server_address[1]
            self.host = self.url_name + ':' + str(self.port)
            self.url = self.scheme + '://' + self.host + self.route
            self.server_thread = threading.Thread(target=self.server.serve_forever, kwargs={'poll_interval': .05}, daemon=True)
            self.server_thread.start()
            self.watch = threading.Thread(target=self._watch, daemon=True)
            self.watch.start()
            return self
        except BaseException:
            self.stop()
            raise

    def _watch(self):
        if not self.cancel.wait(self.lifetime):
            self.emit(('expired', '共有の有効時間が終了しました。'))
        self.stop()

    def receive(self, files):
        mime, body, records = native_body(files)
        connection = http.client.HTTPConnection('127.0.0.1', self.native_port, timeout=10)
        pending = None
        try:
            connection.request('POST', '/receive/' + self.native_token, body, {'Content-Type': mime})
            response = connection.getresponse()
            if response.status != 200:
                raise ValueError('native receive failed')
            response.read(1024 * 1024)
            verified = verified_files(self.output, records)
            if self.cancel.is_set():
                raise TimeoutError('stopped')
            pending = Path(tempfile.mkdtemp(prefix='.kiwi-receive-', suffix='.partial', dir=self.destination))
            for name, payload in verified:
                if self.cancel.is_set():
                    raise TimeoutError('stopped')
                with (pending / name).open('xb') as stream:
                    stream.write(payload)
            final = self.destination / ('受信-' + time.strftime('%Y%m%d-%H%M%S-') + secrets.token_hex(8))
            if self.cancel.is_set():
                raise TimeoutError('stopped')
            pending.rename(final)
            pending = None
            return final
        finally:
            connection.close()
            if pending is not None:
                shutil.rmtree(pending)
            for row in records:
                (self.output / row['internal']).unlink(missing_ok=True)

    def stop(self):
        self.cancel.set()
        with self.stop_lock:
            if self.job:
                self.job.close()
                self.job = None
            if self.proc:
                if self.proc.poll() is None:
                    self.proc.kill()
                self.proc.wait(timeout=5)
            if self.server:
                if self.server_thread and self.server_thread.is_alive():
                    self.server.shutdown()
                self.server.stop_clients()
                self.server.server_close()
                self.server = None
            if self.server_thread:
                self.server_thread.join(timeout=5)
            if self.reader:
                self.reader.join(timeout=5)
                self.proc.stdout.close()
            if self.work:
                self.work.cleanup()
                self.work = None
