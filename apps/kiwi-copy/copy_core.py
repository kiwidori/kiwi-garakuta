"""Compare two local trees and add verified files without replacing existing data."""
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import subprocess
import tempfile
import time

from consumer_runtime import Engine, NativeJob, safe_path, check

MAX_FILES = 2000
MAX_FILE = 512 * 1024**2
MAX_TOTAL = 2 * 1024**3


class BoundedCancel:
    def __init__(self, parent):
        self.parent = parent
        self.deadline = time.monotonic() + 600

    def is_set(self):
        if time.monotonic() > self.deadline:
            raise ValueError('処理が10分を超えたため停止しました。')
        return self.parent.is_set()


class LocalEngine(Engine):
    def call(self, args, work, cancel, *, timeout=600):
        """Run only the fixed local backend, without inherited rclone settings."""
        work = Path(work)
        env = {k: v for k, v in os.environ.items() if not k.upper().startswith('RCLONE_')}
        env.update({'RCLONE_CONFIG': str(work / 'empty.conf')})
        (work / 'empty.conf').write_bytes(b'')
        base = ['--config', str(work / 'empty.conf'), '--local-encoding', 'None',
                '--checkers', '2', '--transfers', '2', '--retries', '1', '--low-level-retries', '1',
                '--stats', '0', '--log-level', 'ERROR', '--contimeout', '10s', '--timeout', '60s']
        check(cancel)
        with (work / 'stdout.log').open('wb') as out, (work / 'stderr.log').open('wb') as err:
            group = NativeJob()
            try:
                p = subprocess.Popen([str(self.executable()), *base, *map(str, args)],
                                     stdin=subprocess.DEVNULL, stdout=out, stderr=err, cwd=work,
                                     env=env, creationflags=subprocess.CREATE_NO_WINDOW)
                group.attach(p)
                deadline = time.monotonic() + timeout
                while p.poll() is None:
                    check(cancel)
                    if time.monotonic() > deadline:
                        raise ValueError('処理が10分を超えたため停止しました。')
                    if out.tell() > 8 * 1024**2 or err.tell() > 1024**2:
                        raise ValueError('処理記録が上限を超えました。')
                    time.sleep(.08)
            finally:
                group.close()
                if 'p' in locals():
                    p.wait(timeout=10)
        check(cancel)
        if (work / 'stdout.log').stat().st_size > 8 * 1024**2 or (work / 'stderr.log').stat().st_size > 1024**2:
            raise ValueError('処理記録が上限を超えました。')
        if p.returncode:
            raise ValueError('フォルダーを処理できませんでした。\n' + (work / 'stderr.log').read_bytes()[-1800:].decode('utf8', 'replace'))
        return (work / 'stdout.log').read_bytes()


def part_ok(name):
    return (bool(name) and len(name) <= 200 and name not in {'.', '..'} and
            not name.endswith((' ', '.')) and not re.search(r'[<>:"/\\|?*\x00-\x1f]', name) and
            not re.fullmatch(r'(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\..*)?', name, re.I))


def root_path(value):
    p = Path(value)
    if not value or not p.is_absolute() or not re.match(r'^[A-Za-z]:[\\/]', str(value)):
        raise ValueError('ドライブ文字から始まるローカルフォルダーを選んでください。')
    if '..' in p.parts or any(not part_ok(s) for s in p.parts[1:]):
        raise ValueError('このフォルダー名には対応していません。')
    return safe_path(p, True)


def roots(source, target):
    a, b = root_path(source), root_path(target)
    if a == b or a in b.parents or b in a.parents:
        raise ValueError('コピー元とコピー先は、別々のフォルダーを選んでください。親子関係のある場所は使えません。')
    return a, b


def stamp(p):
    s = p.stat()
    return [s.st_size, s.st_mtime_ns, s.st_dev, s.st_ino]


def scan(root, cancel, ignore=None):
    """Validate before calling rclone; include empty directories and case collisions."""
    root = root_path(str(root))
    files, dirs, seen, total = {}, [], set(), 0
    stack = [root]
    while stack:
        check(cancel)
        folder = safe_path(stack.pop(), True)
        for p in sorted(folder.iterdir(), key=lambda q: q.name.casefold()):
            check(cancel)
            if ignore is not None and p == ignore:
                continue
            rel = p.relative_to(root).as_posix()
            if len(str(p)) > 240 or any(not part_ok(s) for s in PurePosixPath(rel).parts):
                raise ValueError('長すぎるパス・特殊な名前があります：' + rel)
            if rel.casefold() in seen:
                raise ValueError('大文字・小文字だけが違う名前があります：' + rel)
            seen.add(rel.casefold())
            if len(seen) > MAX_FILES:
                raise ValueError('各フォルダーのファイルとサブフォルダーは合計2,000件までです。')
            safe_path(p)
            s = p.stat()
            if stat.S_ISDIR(s.st_mode):
                dirs.append(rel)
                stack.append(p)
            elif stat.S_ISREG(s.st_mode):
                if s.st_size > MAX_FILE:
                    raise ValueError('1ファイル512 MiBまでです：' + rel)
                total += s.st_size
                if total > MAX_TOTAL:
                    raise ValueError('各フォルダーのファイルは合計2 GiBまでです。')
                files[rel] = stamp(p)
            else:
                raise ValueError('通常ファイル以外は扱えません：' + rel)
    return {'files': files, 'dirs': sorted(dirs)}


def digest(path, cancel):
    safe_path(path)
    before = stamp(path)
    if before[0] > MAX_FILE:
        raise ValueError('ファイルが上限を超えました。')
    h = hashlib.md5(usedforsecurity=False)
    total = 0
    with path.open('rb') as f:
        while chunk := f.read(1024**2):
            check(cancel)
            total += len(chunk)
            if total > MAX_FILE:
                raise ValueError('ファイルが処理中に変わりました。')
            h.update(chunk)
    if before != stamp(path) or total != before[0]:
        raise ValueError('ファイルが処理中に変わりました。もう一度比較してください。')
    return h.hexdigest()


def inventory(engine, root, cancel):
    before = scan(root, cancel)
    with tempfile.TemporaryDirectory(prefix='kiwi-copy-list-') as td:
        raw = engine.call(['lsjson', str(root), '--recursive', '--files-only', '--hash', '--hash-type', 'MD5', '--no-mimetype'], Path(td), cancel)
    rows = json.loads(raw)
    if not isinstance(rows, list) or len(rows) > MAX_FILES:
        raise ValueError('ファイル一覧を確認できません。')
    hashes = {}
    for row in rows:
        rel = row.get('Path')
        h = row.get('Hashes', {}).get('md5', '')
        if (not isinstance(rel, str) or rel not in before['files'] or rel in hashes or row.get('IsDir') or
                row.get('Size') != before['files'][rel][0] or not re.fullmatch('[a-f0-9]{32}', h)):
            raise ValueError('ファイル一覧が処理中に変わったか、対応しない名前があります。')
        hashes[rel] = h
    if set(hashes) != set(before['files']) or scan(root, cancel) != before:
        raise ValueError('フォルダーが処理中に変わりました。もう一度比較してください。')
    return {'tree': before, 'hashes': hashes}


def compare(engine, source, target, cancel):
    cancel = BoundedCancel(cancel)
    a, b = roots(source, target)
    left, right = inventory(engine, a, cancel), inventory(engine, b, cancel)
    # Windows destinations cannot contain both a file and a folder under the same name.
    lf = {k.casefold(): k for k in left['hashes']}
    rf = {k.casefold(): k for k in right['hashes']}
    rd = {k.casefold(): k for k in right['tree']['dirs']}
    rows = []
    for key, rel in lf.items():
        if key in rd or any(p.as_posix().casefold() in rf for p in PurePosixPath(rel).parents if str(p) != '.'):
            status = '名前の衝突'
        elif key not in rf:
            status = '追加予定'
        else:
            other = rf[key]
            status = '同じ内容' if (left['tree']['files'][rel][0] == right['tree']['files'][other][0] and left['hashes'][rel] == right['hashes'][other]) else '内容が異なる（保持）'
        rows.append({'path': rel, 'status': status, 'size': left['tree']['files'][rel][0]})
    for key, rel in rf.items():
        if key not in lf:
            rows.append({'path': rel, 'status': 'コピー先だけ（保持）', 'size': right['tree']['files'][rel][0]})
    return {'source': str(a), 'target': str(b), 'left': left, 'right': right, 'rows': rows}


def apply(engine, plan, cancel, progress=lambda msg: None):
    cancel = BoundedCancel(cancel)
    a, b = roots(plan['source'], plan['target'])
    added = []
    with tempfile.TemporaryDirectory(prefix='.kiwi-copy-', dir=b) as td:
        work = Path(td)
        try:
            if scan(a, cancel) != plan['left']['tree'] or scan(b, cancel, work) != plan['right']['tree']:
                raise ValueError('比較後にフォルダーが変わりました。もう一度比較してください。')
            targets = [r['path'] for r in plan['rows'] if r['status'] == '追加予定']
            if not targets:
                raise ValueError('追加するファイルがありません。')
            merged_dirs = {d.casefold() for d in plan['right']['tree']['dirs']}
            for rel in targets:
                merged_dirs.update(p.as_posix().casefold() for p in PurePosixPath(rel).parents if str(p) != '.')
            projected_count = len(plan['right']['tree']['files']) + len(targets) + len(merged_dirs)
            projected_size = sum(s[0] for s in plan['right']['tree']['files'].values()) + sum(plan['left']['tree']['files'][r][0] for r in targets)
            if projected_count > MAX_FILES or projected_size > MAX_TOTAL:
                raise ValueError('コピー後のフォルダーが2,000件・合計2 GiBの上限を超えます。対象を小さなフォルダーに分けてください。')
            if shutil.disk_usage(b).free < sum(plan['left']['tree']['files'][r][0] for r in targets) + 64 * 1024**2:
                raise ValueError('コピー先の空き容量が不足しています。')
            staged = work / 'files'
            staged.mkdir()
            listing = work / 'files.txt'
            listing.write_text(''.join(r + '\n' for r in targets), encoding='utf8')
            progress('追加するファイルを作業領域へコピーしています…')
            engine.call(['copy', str(a), str(staged), '--files-from-raw', str(listing),
                         '--ignore-existing', '--max-transfer', str(MAX_TOTAL), '--cutoff-mode', 'cautious'], work, cancel)
            progress('コピーした内容を照合しています…')
            result = scan(staged, cancel)
            if set(result['files']) != set(targets):
                raise ValueError('コピーしたファイルが不足しています。')
            for rel in targets:
                check(cancel)
                expected = plan['left']['hashes'][rel]
                if digest(staged / rel, cancel) != expected or digest(a / rel, cancel) != expected:
                    raise ValueError('コピー中に内容が変わりました。もう一度比較してください。')
            if scan(a, cancel) != plan['left']['tree'] or scan(b, cancel, work) != plan['right']['tree']:
                raise ValueError('コピー中にフォルダーが変わりました。もう一度比較してください。')
            progress('照合済みのファイルを追加しています…')
            for rel in targets:
                check(cancel)
                dest = safe_path(b / rel)
                if dest.exists():
                    raise ValueError('コピー先に同名ファイルが作成されました。上書きせず停止します。')
                dest.parent.mkdir(parents=True, exist_ok=True)
                safe_path(dest.parent, True)
                # On Windows, rename fails if the destination appeared in the meantime.
                os.rename(staged / rel, dest)
                added.append(rel)
            return added
        except Exception as error:
            if added:
                raise ValueError(f'{len(added)}件を追加した後に停止しました。追加済みファイルは残しています。再度比較してください。\n' + str(error)) from error
            raise
