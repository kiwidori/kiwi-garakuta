"""Read-only grouping with explicit input paths and independent content verification."""
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import tempfile
import time
from consumer_runtime import Engine, NativeJob, safe_path, check

MAX_ENTRIES = 10000
MAX_FILE = 512 * 1024**2
MAX_TOTAL = 8 * 1024**3
DEPTHS = {'すべて': None, '直下だけ': 0, '2階層まで': 1, '3階層まで': 2}


class Deadline:
    def __init__(self, parent):
        self.parent = parent
        self.end = time.monotonic() + 600

    def is_set(self):
        if time.monotonic() > self.end:
            raise ValueError('検索が10分を超えたため停止しました。')
        return self.parent.is_set()


class DuplicateEngine(Engine):
    def group(self, paths, unique, copies, work, cancel):
        deadline = time.monotonic() + 600
        work = Path(work)
        env = {k: v for k, v in os.environ.items() if not k.upper().startswith(('FCLONES_', 'RUST_', 'RAYON_'))}
        args = ['group', '--format', 'json', '--hash-fn', 'sha256', '--threads', 'main:2',
                '--threads', 'default:2', '--stdin', '--depth', '0', '--hidden', '--no-ignore',
                '--min', '0', '--max', str(MAX_FILE)]
        args += ['--unique'] if unique else ['--rf-over', str(copies - 1)]
        source = work / 'files.txt'
        source.write_text(''.join(str(p) + '\n' for p in paths), encoding='utf8')
        check(cancel)
        with source.open('rb') as inp, (work / 'result.json').open('wb') as out, (work / 'error.log').open('wb') as err:
            job = NativeJob()
            try:
                p = subprocess.Popen([str(self.executable()), *args], cwd=work, env=env, stdin=inp,
                                     stdout=out, stderr=err, creationflags=subprocess.CREATE_NO_WINDOW)
                job.attach(p)
                while p.poll() is None:
                    check(cancel)
                    if time.monotonic() > deadline:
                        raise ValueError('検索が10分を超えたため停止しました。')
                    if out.tell() > 8 * 1024**2 or err.tell() > 1024**2:
                        raise ValueError('検索結果が上限を超えました。')
                    time.sleep(.08)
            finally:
                job.close()
                if 'p' in locals():
                    p.wait(timeout=10)
        check(cancel)
        if (work / 'result.json').stat().st_size > 8 * 1024**2 or (work / 'error.log').stat().st_size > 1024**2:
            raise ValueError('検索結果が上限を超えました。')
        if p.returncode:
            raise ValueError('ファイルを検索できませんでした。権限や使用中のファイルを確認してください。')
        return json.loads((work / 'result.json').read_bytes())


def root(value):
    p = Path(value)
    if (not re.match(r'^[A-Za-z]:[\\/]', str(value)) or not p.is_absolute() or '..' in p.parts or
            any(ord(c) < 32 for c in str(value))):
        raise ValueError('ローカルドライブの絶対パスを選んでください。')
    return safe_path(p, True)


def options(v):
    folders = [root(v['folder'])]
    if v['other'].strip():
        folders.append(root(v['other']))
        if folders[0] == folders[1] or folders[0] in folders[1].parents or folders[1] in folders[0].parents:
            raise ValueError('追加対象には、同じ場所や親子関係でないフォルダーを選んでください。')
    if v['depth'] not in DEPTHS or v['mode'] not in {'重複ファイル', '1つだけのファイル'}:
        raise ValueError('検索方法を選んでください。')
    for k in ('min', 'max', 'copies'):
        if not re.fullmatch('[0-9]{1,6}', v[k]):
            raise ValueError('サイズと件数は整数で指定してください。')
    low, high, copies = int(v['min']) * 1024, int(v['max']) * 1024**2, int(v['copies'])
    if not 0 <= low <= high <= MAX_FILE or not 2 <= copies <= 10:
        raise ValueError('最小サイズ≦最大サイズ（512 MiBまで）、重複件数は2～10で指定してください。')
    return folders, low, high, copies, DEPTHS[v['depth']], v['mode'] == '1つだけのファイル'


def stamp(p):
    s = p.stat()
    return [s.st_size, s.st_mtime_ns, s.st_dev, s.st_ino]


def scan(folders, low, high, depth, cancel):
    files, skipped, count, total, seen, ids = {}, 0, 0, 0, set(), set()
    for index, folder in enumerate(folders, 1):
        stack = [(folder, 0)]
        while stack:
            check(cancel)
            parent, level = stack.pop()
            safe_path(parent, True)
            with os.scandir(parent) as entries:
                for entry in entries:
                    check(cancel)
                    count += 1
                    if count > MAX_ENTRIES:
                        raise ValueError('対象のファイルとフォルダーは合計10,000件までです。小さなフォルダーに分けてください。')
                    p = Path(entry.path)
                    name = p.relative_to(folder).as_posix()
                    # DirEntry's cached Windows stat omits file identifiers.
                    s = p.stat(follow_symlinks=False)
                    if (getattr(s, 'st_file_attributes', 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT or
                            stat.S_ISLNK(s.st_mode) or len(str(p)) > 240 or any(ord(c) < 32 for c in name)):
                        skipped += 1
                        continue
                    if (index, name.casefold()) in seen:
                        raise ValueError('大文字・小文字だけが異なるパスには対応していません。')
                    seen.add((index, name.casefold()))
                    if stat.S_ISDIR(s.st_mode):
                        if depth is None or level < depth:
                            stack.append((p, level + 1))
                    elif stat.S_ISREG(s.st_mode):
                        identity = (s.st_dev, s.st_ino)
                        if not low <= s.st_size <= high or (s.st_ino and identity in ids):
                            skipped += 1
                            continue
                        if s.st_ino:
                            ids.add(identity)
                        total += s.st_size
                        if total > MAX_TOTAL:
                            raise ValueError('検索するファイルの合計は8 GiBまでです。対象を小さなフォルダーに分けてください。')
                        files[p] = {'stamp': stamp(p), 'scope': index, 'relative': name}
                    else:
                        skipped += 1
    return files, skipped


def digest(p, cancel):
    safe_path(p)
    before = stamp(p)
    if before[0] > MAX_FILE:
        raise ValueError('ファイルが上限を超えました。')
    h, size = hashlib.sha256(), 0
    with p.open('rb') as f:
        while chunk := f.read(1024**2):
            check(cancel)
            size += len(chunk)
            if size > MAX_FILE:
                raise ValueError('検索中にファイルが変わりました。')
            h.update(chunk)
    if before != stamp(p) or size != before[0]:
        raise ValueError('検索中にファイルが変わりました。もう一度検索してください。')
    return h.hexdigest()


def search(engine, v, cancel, progress=lambda msg: None):
    cancel = Deadline(cancel)
    folders, low, high, copies, depth, unique = options(v)
    files, skipped = scan(folders, low, high, depth, cancel)
    if not files:
        return {'groups': [], 'scanned': 0, 'skipped': skipped, 'unique': unique, 'extra': 0}
    progress(f'{len(files):,}件の内容を調べています…')
    with tempfile.TemporaryDirectory(prefix='kiwi-duplicates-') as td:
        report = engine.group(sorted(files, key=str), unique, copies, Path(td), cancel)
    rows = report.get('groups')
    if not isinstance(rows, list) or len(rows) > len(files):
        raise ValueError('検索結果を確認できませんでした。')
    native, claimed = set(), set()
    for row in rows:
        names = row.get('files')
        if not isinstance(names, list) or not 1 <= len(names) <= len(files):
            raise ValueError('検索結果のファイル一覧が不正です。')
        paths = []
        for name in names:
            p = Path(name)
            if p not in files or p in claimed or row.get('file_len') != files[p]['stamp'][0]:
                raise ValueError('検索対象外のパス、重複したパス、サイズ違いの結果があります。')
            claimed.add(p)
            paths.append(p)
        native.add(frozenset(paths))
    progress('検索結果をSHA-256で再確認しています…')
    hashes = {}
    for p, info in files.items():
        check(cancel)
        if stamp(p) != info['stamp']:
            raise ValueError('検索中にファイルが変わりました。')
        hashes.setdefault((info['stamp'][0], digest(p, cancel)), []).append(p)
    expected = {frozenset(ps) for ps in hashes.values() if (len(ps) == 1 if unique else len(ps) >= copies)}
    if native != expected or scan(folders, low, high, depth, cancel)[0] != files:
        raise ValueError('検索中にファイルが変わったか、結果を照合できませんでした。もう一度検索してください。')
    groups = []
    for (size, h), paths in hashes.items():
        if frozenset(paths) in expected:
            groups.append({'size': size, 'sha256': h, 'files': [dict(files[p], path=str(p)) for p in sorted(paths, key=str)]})
    groups.sort(key=lambda g: (-g['size'] * len(g['files']), g['sha256']))
    return {'groups': groups, 'scanned': len(files), 'skipped': skipped, 'unique': unique,
            'extra': 0 if unique else sum(g['size'] * (len(g['files']) - 1) for g in groups)}
