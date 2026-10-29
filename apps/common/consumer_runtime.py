"""First-use engine setup and bounded desktop jobs."""
import ctypes
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import stat
import subprocess
import tarfile
import tempfile
import time
import urllib.request
import zipfile


class Cancelled(Exception):
    pass


class NativeJob:
    """Close the entire native process group, including one-file launchers."""
    def __init__(self):
        from ctypes import wintypes
        class Basic(ctypes.Structure):
            _fields_ = [('process_time', ctypes.c_int64), ('job_time', ctypes.c_int64),
                        ('flags', wintypes.DWORD), ('min_ws', ctypes.c_size_t), ('max_ws', ctypes.c_size_t),
                        ('active', wintypes.DWORD), ('affinity', ctypes.c_size_t),
                        ('priority', wintypes.DWORD), ('scheduling', wintypes.DWORD)]
        class Extended(ctypes.Structure):
            _fields_ = [('basic', Basic), ('io', ctypes.c_uint64 * 6),
                        ('process_memory', ctypes.c_size_t), ('job_memory', ctypes.c_size_t),
                        ('peak_process', ctypes.c_size_t), ('peak_job', ctypes.c_size_t)]
        self.api = ctypes.WinDLL('kernel32', use_last_error=True)
        self.api.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
        self.api.CreateJobObjectW.restype = wintypes.HANDLE
        self.api.SetInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
        self.api.SetInformationJobObject.restype = wintypes.BOOL
        self.api.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
        self.api.AssignProcessToJobObject.restype = wintypes.BOOL
        self.api.CloseHandle.argtypes = [wintypes.HANDLE]
        self.api.CloseHandle.restype = wintypes.BOOL
        self.handle = self.api.CreateJobObjectW(None, None)
        if not self.handle:
            raise ctypes.WinError(ctypes.get_last_error())
        info = Extended()
        info.basic.flags = 0x2000 | 0x100  # KILL_ON_JOB_CLOSE | PROCESS_MEMORY
        info.process_memory = 512 * 1024**2
        if not self.api.SetInformationJobObject(self.handle, 9, ctypes.byref(info), ctypes.sizeof(info)):
            self.close()
            raise OSError('実行上限を設定できません。')

    def attach(self, proc):
        if not self.api.AssignProcessToJobObject(self.handle, int(proc._handle)):
            proc.kill()
            proc.wait(timeout=10)
            raise OSError('安全な実行グループを作れません。')

    def close(self):
        if self.handle:
            self.api.CloseHandle(self.handle)
            self.handle = None


def check(cancel):
    if cancel.is_set():
        raise Cancelled('停止しました。')


def safe_path(value, directory=False):
    p = Path(value).absolute()
    if str(p).startswith(('\\\\', '//')):
        raise ValueError('ネットワーク上のパスには対応していません。')
    for q in [*reversed(p.parents), p]:
        if q.exists() and (q.is_symlink() or getattr(q.lstat(), 'st_file_attributes', 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT):
            raise ValueError('リンク・ジャンクションは指定できません。')
    if directory and not p.is_dir():
        raise ValueError('フォルダーを確認してください。')
    return p


def local_folder():
    buf = ctypes.create_unicode_buffer(32768)
    if os.name != 'nt' or ctypes.windll.shell32.SHGetFolderPathW(None, 0x001c, None, 0, buf) != 0:
        raise OSError('Windowsの保存先を取得できません。')
    return Path(buf.value)


class Engine:
    def __init__(self, root):
        self.root = Path(root)
        self.pin = json.loads((self.root / 'upstream-pin.json').read_text(encoding='utf8'))
        self.cache = local_folder() / self.pin['cache']

    def executable(self):
        p = safe_path(self.cache / self.pin['executable'])
        if not p.is_file():
            raise ValueError('先に「エンジンを準備」を押してください。')
        return p

    def install(self, cancel, progress):
        parent = safe_path(self.cache.parent)
        parent.mkdir(parents=True, exist_ok=True)
        if self.cache.exists():
            return self.executable()
        pin = self.pin
        with tempfile.TemporaryDirectory(prefix='setup-', dir=parent) as td:
            work = Path(td)
            archive = work / 'download'
            total = 0
            digest = hashlib.sha256()
            deadline = time.monotonic() + 600
            request = urllib.request.Request(pin['url'], headers={'User-Agent': 'KiwiDesktop/0.1'})
            with urllib.request.urlopen(request, timeout=30) as response, archive.open('xb') as target:
                while chunk := response.read(512 * 1024):
                    check(cancel)
                    total += len(chunk)
                    if total > pin['size'] or time.monotonic() > deadline:
                        raise ValueError('取得サイズ・時間の上限を超えました。')
                    target.write(chunk)
                    digest.update(chunk)
                    progress(f'公式エンジンを取得中 {total / 1024**2:.1f} MiB')
            if total != pin['size'] or digest.hexdigest() != pin['sha256']:
                raise ValueError('ダウンロードの検証に失敗しました。')
            out = work / 'files'
            out.mkdir()
            found = set()

            def put(name, data):
                check(cancel)
                q = PurePosixPath(name)
                if q.is_absolute() or '..' in q.parts or '\\' in name or any(':' in x for x in q.parts):
                    raise ValueError('書庫のパスが不正です。')
                if name in found or name not in pin['members'] or len(data) > 300 * 1024**2:
                    raise ValueError('書庫の内容が不正です。')
                if hashlib.sha256(data).hexdigest() != pin['members'][name]:
                    raise ValueError('展開ファイルの検証に失敗しました。')
                dest = out.joinpath(*q.parts)
                dest.parent.mkdir(parents=True, exist_ok=True)
                with dest.open('xb') as f:
                    f.write(data)
                found.add(name)

            if pin['kind'] == 'zip':
                with zipfile.ZipFile(archive) as z:
                    if sum(x.file_size for x in z.infolist()) > 400 * 1024**2:
                        raise ValueError('展開サイズが上限を超えました。')
                    for m in z.infolist():
                        if m.is_dir():
                            continue
                        if (m.external_attr >> 16) & 0o170000 == 0o120000:
                            raise ValueError('リンクは展開できません。')
                        put(m.filename, z.read(m))
            elif pin['kind'] == 'tar':
                with tarfile.open(archive) as z:
                    members = z.getmembers()
                    if sum(m.size for m in members) > 400 * 1024**2:
                        raise ValueError('展開サイズが上限を超えました。')
                    for m in members:
                        if m.isdir():
                            continue
                        if not m.isfile():
                            raise ValueError('通常ファイル以外は展開できません。')
                        put(m.name, z.extractfile(m).read())
            else:
                put(pin['executable'], archive.read_bytes())
            if found != set(pin['members']):
                raise ValueError('展開ファイルが不足しています。')
            check(cancel)
            out.rename(self.cache)
        return self.executable()

    def call(self, args, work, cancel, *, timeout=180, stdin=None, env=None, cap=64 * 1024**2):
        work = Path(work)
        check(cancel)
        clean_env = os.environ.copy()
        for key in list(clean_env):
            if key.startswith(('F2_', 'DUCKDB_', 'PANDOC_')):
                clean_env.pop(key)
        if env:
            clean_env.update(env)
        input_path = work / 'stdin.txt'
        input_path.write_bytes(stdin or b'')
        with input_path.open('rb') as source, (work / 'stdout.log').open('wb') as out, (work / 'stderr.log').open('wb') as err:
            group = NativeJob()
            try:
                proc = subprocess.Popen([str(self.executable()), *map(str, args)], cwd=work, stdin=source,
                                        stdout=out, stderr=err, env=clean_env, creationflags=subprocess.CREATE_NO_WINDOW)
                group.attach(proc)
            except BaseException:
                group.close()
                raise
            deadline = time.monotonic() + timeout
            try:
                while proc.poll() is None:
                    check(cancel)
                    if time.monotonic() > deadline:
                        raise ValueError('処理の時間制限を超えました。')
                    sizes = [p.stat().st_size for p in work.rglob('*') if p.is_file()]
                    if any(size > cap for size in sizes) or sum(sizes) > cap * 2:
                        raise ValueError('出力サイズの上限を超えました。')
                    time.sleep(.08)
            finally:
                group.close()
                proc.wait(timeout=10)
        check(cancel)
        sizes = [p.stat().st_size for p in work.rglob('*') if p.is_file()]
        if any(size > cap for size in sizes) or sum(sizes) > cap * 2:
            raise ValueError('出力サイズの上限を超えました。')
        raw = (work / 'stdout.log').read_bytes()
        if proc.returncode:
            error = (work / 'stderr.log').read_bytes()[-2200:].decode('utf8', 'replace')
            raise ValueError('処理できませんでした。設定と入力を確認してください。\n' + error)
        return raw


def stage(value, work, cancel, extensions, limit=64 * 1024**2):
    p = safe_path(value)
    if not p.is_file() or p.suffix.lower() not in extensions or not 0 < p.stat().st_size <= limit:
        raise ValueError('対応する形式・容量のファイルを選んでください。')
    if shutil.disk_usage(work).free < limit * 3:
        raise ValueError('作業用の空き領域が不足しています。')
    dest = Path(work) / ('input' + p.suffix.lower())
    total = 0
    with p.open('rb') as src, dest.open('xb') as dst:
        while chunk := src.read(1024**2):
            check(cancel)
            total += len(chunk)
            if total > limit:
                raise ValueError('入力が大きすぎます。')
            dst.write(chunk)
    return dest


def save_file(source, folder, stem, suffix, cancel):
    folder = safe_path(folder, True)
    stem = ''.join(c for c in stem if c not in '<>:"/\\|?*' and ord(c) >= 32).strip(' .')[:80] or 'result'
    for n in range(1000):
        dest = folder / (stem + (f'_{n}' if n else '') + suffix)
        try:
            with dest.open('xb') as target:
                try:
                    with Path(source).open('rb') as src:
                        while chunk := src.read(1024**2):
                            check(cancel)
                            target.write(chunk)
                except BaseException:
                    target.close()
                    dest.unlink()
                    raise
            return dest
        except FileExistsError:
            continue
    raise ValueError('同名ファイルが多すぎます。')
