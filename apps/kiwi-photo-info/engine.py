"""Read metadata and write only copies in a new output directory."""
import csv
import datetime
import io
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request
import zipfile

ROOT = Path(sys.executable).parent if getattr(sys, 'frozen', False) else Path(__file__).resolve().parent
LIMIT = 256 * 1024**2
WRITABLE = {'.jpg', '.jpeg', '.png', '.webp'}
TAG = re.compile(r'(?:EXIF|IPTC|XMP(?:-[A-Za-z0-9]+)?):[A-Za-z][A-Za-z0-9-]{0,79}\Z')
DOWNLOAD_URL = 'https://downloads.sourceforge.net/project/exiftool/exiftool-13.59_64.zip'
DOWNLOAD_SHA256 = '44b512b25af500724ba579d0a53c8fc5851628b692dd5e5d94ae4a15c2cba9ec'


def prepare(cancel, progress=lambda text: None):
    """Obtain the original upstream package directly, with its notices intact."""
    if (ROOT/'native').exists():
        raise ValueError('nativeフォルダーは既にあります。既存のツールは置き換えません。')
    stage = Path(tempfile.mkdtemp(prefix='.kiwi-exiftool-', dir=ROOT))
    started = time.monotonic()
    try:
        archive = stage/'official.zip'
        with urllib.request.urlopen(DOWNLOAD_URL, timeout=20) as response, archive.open('xb') as out:
            while chunk := response.read(64*1024):
                check(cancel)
                if time.monotonic()-started > 120:
                    raise TimeoutError('取得が2分を超えました。通信環境を確認して再度お試しください。')
                out.write(chunk)
                if out.tell() > 16*1024**2:
                    raise ValueError('ダウンロードサイズが上限を超えました。')
                progress(f'公式ExifToolを取得中… {out.tell()//1024} KiB')
        if hashlib.sha256(archive.read_bytes()).hexdigest() != DOWNLOAD_SHA256:
            raise ValueError('公式配布物のハッシュが一致しません。取得を中止しました。')
        unpack = stage/'unpack'
        with zipfile.ZipFile(archive) as z:
            total = 0
            if len(z.infolist()) > 5000:
                raise ValueError('配布物の件数を確認できません。')
            for entry in z.infolist():
                check(cancel)
                target = unpack / entry.filename
                if not target.resolve().is_relative_to(unpack.resolve()) or '\\' in entry.filename or ':' in entry.filename:
                    raise ValueError('配布物に不正なパスがあります。')
                total += entry.file_size
                if total > 128*1024**2 or (entry.external_attr >> 16) & 0o170000 == 0o120000:
                    raise ValueError('配布物の構成を確認できません。')
                z.extract(entry, unpack)
        source = unpack/'exiftool-13.59_64'
        if not (source/'exiftool_files/perl.exe').is_file():
            raise ValueError('配布物に実行ファイルがありません。')
        check(cancel)
        source.rename(ROOT/'native')
        return ROOT/'native'
    finally:
        shutil.rmtree(stage)


def check(cancel):
    if cancel.is_set():
        raise InterruptedError('停止しました。')


def checked_path(value, directory=False):
    p = Path(os.path.abspath(value))
    for part in [*reversed(p.parents), p]:
        if part.exists() and (part.is_symlink() or getattr(part.lstat(), 'st_file_attributes', 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT):
            raise ValueError('リンク・ジャンクションは指定できません。')
    if directory:
        if not p.is_dir():
            raise ValueError('保存先フォルダーを選んでください。')
    elif not p.is_file() or not 0 < p.stat().st_size <= LIMIT:
        raise ValueError('空でない256 MiB以下の通常ファイルを指定してください。')
    return p


def call(args, cancel, timeout=300, cap=16*1024**2):
    check(cancel)
    base = ROOT / 'native' / 'exiftool_files'
    if not (base/'perl.exe').is_file():
        raise ValueError('初回のみ「ExifToolを準備」から公式ツールを取得してください。')
    if any(any(c in str(arg) for c in '\r\n\x00') for arg in args):
        raise ValueError('改行を含む引数は指定できません。')
    env = {k: v for k, v in os.environ.items() if not k.upper().startswith(('PERL', 'EXIFTOOL', 'LC_'))}
    env['LANG'] = 'C'
    command = [str(base/'perl.exe'), '-Ilib', 'exiftool.pl', '-config', '', '-charset', 'filename=utf8', '-@', '-']
    proc = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            cwd=base, env=env, creationflags=subprocess.CREATE_NO_WINDOW)
    buffers = [bytearray(), bytearray()]
    overflow = threading.Event()
    def read(stream, index):
        try:
            while chunk := stream.read(8192):
                if len(buffers[index]) + len(chunk) > cap:
                    overflow.set()
                    break
                buffers[index].extend(chunk)
        finally:
            stream.close()
    readers = [threading.Thread(target=read, args=(stream, index), daemon=True)
               for index, stream in enumerate((proc.stdout, proc.stderr))]
    for t in readers:
        t.start()
    def send():
        try:
            proc.stdin.write(('\n'.join(args)+'\n').encode('utf8'))
            proc.stdin.close()
        except (BrokenPipeError, OSError):
            pass
    writer = threading.Thread(target=send, daemon=True)
    writer.start()
    deadline = time.monotonic() + timeout
    try:
        while proc.poll() is None:
            check(cancel)
            if overflow.is_set():
                raise ValueError('読み取り結果が16 MiBを超えました。')
            if time.monotonic() > deadline:
                raise TimeoutError('処理が5分を超えました。対象を減らしてください。')
            time.sleep(.03)
        for t in readers:
            t.join()
        check(cancel)
        if overflow.is_set():
            raise ValueError('読み取り結果が上限を超えました。')
        error = buffers[1].decode('utf8', 'replace').strip()
        if proc.returncode:
            raise ValueError(error[:1500] or '元ツールで処理できませんでした。')
        return bytes(buffers[0]), error
    finally:
        if proc.poll() is None:
            proc.kill()
        proc.wait()
        for t in readers:
            t.join(timeout=5)
        writer.join(timeout=5)


def inspect(files, cancel):
    if not 1 <= len(files) <= 100:
        raise ValueError('1～100ファイルを選んでください。')
    results = []
    started = time.monotonic()
    total = 0
    volume = 0
    for name in files:
        p = checked_path(name)
        volume += p.stat().st_size
        if volume > 1024**3:
            raise ValueError('一括処理は合計1 GiBまでです。')
        remaining = 300-(time.monotonic()-started)
        if remaining <= 0:
            raise TimeoutError('一括読み取りは5分までです。')
        raw, warning = call(['-j', '-G1:4', '-a', '-s', '-n', str(p)], cancel, remaining)
        total += len(raw)
        if total > 16*1024**2:
            raise ValueError('一括読み取りの結果が16 MiBを超えました。')
        if not raw.strip():
            raise ValueError(warning[:1500] or 'ファイルの情報を読み取れませんでした。')
        item = json.loads(raw.decode('utf8'))[0]
        if item.get('ExifTool:Error'):
            raise ValueError(str(item['ExifTool:Error']))
        if warning:
            item['Kiwi:Warning'] = warning
        results.append(item)
    return results


def edit_args(options):
    mode = options['mode']
    if mode == 'gps':
        return ['-GPS:all=', '-XMP:GPS*=', '-XMP:Location*=', '-XMP:City=', '-XMP:State=', '-XMP:Country=',
                '-IPTC:City=', '-IPTC:Sub-location=', '-IPTC:Province-State=', '-IPTC:Country-PrimaryLocationName=']
    if mode == 'clean':
        return ['-all=', '-tagsFromFile', '@', '-Orientation', '-ICC_Profile'] if options.get('appearance', True) else ['-all=']
    if mode == 'edit':
        values = options.get('values', {})
        if not values or len(values) > 30:
            raise ValueError('変更する項目を1～30個指定してください。')
        args = []
        for tag, value in values.items():
            if not TAG.fullmatch(tag) or len(value) > 4096 or any(c in value for c in '\x00\r\n'):
                raise ValueError('タグ名・値を確認してください。EXIF、IPTC、XMPのタグを指定できます。')
            if tag in ('EXIF:DateTimeOriginal', 'EXIF:CreateDate', 'EXIF:ModifyDate') and value:
                datetime.datetime.strptime(value, '%Y:%m:%d %H:%M:%S')
            args.append('-'+tag+'='+value)
        return args
    if mode == 'shift':
        hours = int(options['hours'])
        if not -168 <= hours <= 168 or hours == 0:
            raise ValueError('時刻差は-168～168時間（0以外）です。')
        return [f'-AllDates{"+" if hours > 0 else "-"}=0:0:0 {abs(hours)}:0:0']
    if mode == 'copy':
        return ['-tagsFromFile', str(checked_path(options['source'])), '-all:all']
    if mode == 'xmp':
        return []
    raise ValueError('操作を選んでください。')


def process(files, destination, options, cancel, progress=lambda text: None):
    started = time.monotonic()
    if not 1 <= len(files) <= 100:
        raise ValueError('1～100ファイルを選んでください。')
    paths = [checked_path(p) for p in files]
    if sum(p.stat().st_size for p in paths) > 1024**3:
        raise ValueError('一括処理は合計1 GiBまでです。')
    if any(p.suffix.lower() not in WRITABLE for p in paths):
        raise ValueError('保存処理はJPEG・PNG・WebPに対応します。その他は情報の確認のみです。')
    parent = checked_path(destination, directory=True)
    args = edit_args(options)
    for p in paths:
        remaining = 300-(time.monotonic()-started)
        if remaining <= 0:
            raise TimeoutError('一括処理は5分までです。')
        raw, _ = call(['-j', '-n', '-FileType', str(p)], cancel, remaining)
        if not raw.strip() or json.loads(raw)[0].get('FileType') not in {'JPEG', 'PNG', 'WEBP', 'Extended WEBP'}:
            raise ValueError('保存処理には実際の内容がJPEG・PNG・WebPのファイルを指定してください。')
    snap = {p: (p.stat().st_size, p.stat().st_mtime_ns) for p in paths}
    stage = Path(tempfile.mkdtemp(prefix='.kiwi-photo-', dir=parent))
    final = parent / ('写真情報-'+time.strftime('%Y%m%d-%H%M%S')+'-'+os.urandom(3).hex())
    report = []
    try:
        for index, source in enumerate(paths, 1):
            check(cancel)
            progress(f'{index}/{len(paths)}  {source.name}')
            target = stage / f'{index:03d}-{source.name}'
            remaining = 300 - (time.monotonic()-started)
            if remaining <= 0:
                raise TimeoutError('一括処理は5分までです。対象を減らしてください。')
            if options['mode'] == 'xmp':
                target = target.with_suffix('.xmp')
                _, warning = call(['-o', str(target), str(source)], cancel, remaining)
            else:
                shutil.copyfile(source, target)
                _, warning = call(['-overwrite_original', *args, str(target)], cancel, remaining)
            if not target.is_file() or target.stat().st_size > LIMIT:
                raise ValueError('保存結果を確認できませんでした。')
            report.append({'file': target.name, 'warning': warning})
        for p, before in snap.items():
            if (p.stat().st_size, p.stat().st_mtime_ns) != before:
                raise ValueError('処理中に元ファイルが変更されました。やり直してください。')
        check(cancel)
        stage.rename(final)
        return final, report
    finally:
        if stage.exists():
            shutil.rmtree(stage)


def export_report(data, kind):
    if kind == 'json':
        return json.dumps(data, ensure_ascii=False, indent=2)
    buffer = io.StringIO(newline='')
    writer = csv.writer(buffer)
    writer.writerow(['ファイル', 'グループ・タグ', '値'])
    for item in data:
        for tag, value in item.items():
            text = str(value) if not isinstance(value, (list, dict)) else json.dumps(value, ensure_ascii=False)
            # Keep spreadsheet applications from treating metadata as a formula.
            writer.writerow(["'"+str(item.get('SourceFile', '')), tag, "'"+text])
    return '\ufeff'+buffer.getvalue()
