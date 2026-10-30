"""Create bounded snapshots of explicitly selected files and folders."""
import os
from pathlib import Path
import stat
import zipfile

from upload_gate import filename

MAX_BYTES = 256 * 1024**2
MAX_FILES = 1000


def ordinary(path):
    info = path.lstat()
    if (stat.S_ISLNK(info.st_mode) or getattr(info, 'st_file_attributes', 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT
            or not (stat.S_ISDIR(info.st_mode) or stat.S_ISREG(info.st_mode))):
        raise ValueError('リンクや特殊なファイルは送れません。')
    return info


def prepare(paths, directory, cancel, *, note='', force_zip=False):
    """Return a private snapshot; caller owns the newly allocated directory."""
    directory = Path(directory)
    if not directory.is_dir() or any(directory.iterdir()):
        raise ValueError('作業用フォルダーが空ではありません。')
    if cancel.is_set():
        raise InterruptedError('停止しました。')
    if note:
        if paths or len(note.encode('utf8')) > 1024**2:
            raise ValueError('メモはファイルを選ばず、1 MiB以下で入力してください。')
        file = directory / 'メモ.txt'
        file.write_text(note, encoding='utf8')
        return file
    if not 1 <= len(paths) <= 100:
        raise ValueError('送るファイル・フォルダーを1～100件選んでください。')
    selected = []
    top_names = set()
    total = 0
    for value in paths:
        path = Path(value).absolute()
        info = ordinary(path)
        name = filename(path.name)
        if name.casefold() in top_names:
            raise ValueError('同じ名前のファイルやフォルダーは分けて送ってください。')
        top_names.add(name.casefold())
        if stat.S_ISDIR(info.st_mode):
            force_zip = True
            selected.append((path, name + '/', True))
            for parent, dirs, files in os.walk(path, followlinks=False, onerror=lambda e: (_ for _ in ()).throw(e)):
                if cancel.is_set():
                    raise InterruptedError('停止しました。')
                for entry in sorted(dirs + files):
                    child = Path(parent) / entry
                    info = ordinary(child)
                    filename(child.name)
                    is_dir = stat.S_ISDIR(info.st_mode)
                    arc = name + '/' + child.relative_to(path).as_posix() + ('/' if is_dir else '')
                    selected.append((child, arc, is_dir))
                    if not is_dir:
                        total += info.st_size
                    if len(selected) > MAX_FILES or total > MAX_BYTES:
                        raise ValueError('送信は1000項目・合計256 MiBまでです。')
        else:
            selected.append((path, name, False))
            total += info.st_size
        if len(selected) > MAX_FILES or total > MAX_BYTES:
            raise ValueError('送信は1000項目・合計256 MiBまでです。')
    if cancel.is_set():
        raise InterruptedError('停止しました。')
    if len({arc.casefold() for _, arc, _ in selected}) != len(selected):
        raise ValueError('Windowsで同じ名前になる項目が含まれています。')
    output = directory / ('共有ファイル.zip' if force_zip or len(paths) > 1 else selected[0][1])
    written = 0

    def chunks(path):
        nonlocal written
        ordinary(path)
        with path.open('rb') as stream:
            while data := stream.read(65536):
                if cancel.is_set():
                    raise InterruptedError('停止しました。')
                written += len(data)
                if written > MAX_BYTES:
                    raise ValueError('送信するファイルが256 MiBを超えました。')
                yield data

    try:
        if force_zip or len(paths) > 1:
            with zipfile.ZipFile(output, 'x', compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
                for path, arc, is_dir in selected:
                    if cancel.is_set():
                        raise InterruptedError('停止しました。')
                    if is_dir:
                        archive.writestr(arc, b'')
                    else:
                        with archive.open(arc, 'w') as target:
                            for data in chunks(path):
                                target.write(data)
        else:
            with output.open('xb') as target:
                for data in chunks(selected[0][0]):
                    target.write(data)
        return output
    except BaseException:
        output.unlink(missing_ok=True)
        raise
