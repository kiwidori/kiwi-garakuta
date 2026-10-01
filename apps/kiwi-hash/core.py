"""Bounded read-only b3sum invocation."""
import sys
import re
import time
import tempfile
import subprocess
from pathlib import Path

def resource_dir():
    return Path(sys._MEIPASS) if getattr(sys,'frozen',False) else Path(__file__).resolve().parent

def normalize_expected(text):
    value=text.strip().lower()
    if value and re.fullmatch('[0-9a-f]{64}',value) is None:
        raise ValueError('照合値は64文字のBLAKE3ハッシュを入力してください。')
    return value

def signature(path):
    stat=path.stat()
    return (stat.st_dev,stat.st_ino,stat.st_size,stat.st_mtime_ns)

def hash_file(exe,source,cancel):
    source=Path(source).resolve()
    if not source.is_file():
        raise ValueError('計算するファイルを選んでください。')
    before=signature(source)
    if before[2]>8*1024**3:
        raise ValueError('対象ファイルは8 GiBまでです。')
    if not exe.is_file():
        raise ValueError('同梱のb3sum.exeが見つかりません。')
    if cancel.is_set():
        raise InterruptedError()
    with tempfile.TemporaryDirectory(prefix='kiwi-hash-') as temp:
        folder=Path(temp)
        stdout=folder/'hash.txt'
        stderr=folder/'error.txt'
        cmd=[str(exe.resolve()),'--no-names','--no-mmap','--',str(source)]
        with stdout.open('wb') as out,stderr.open('wb') as err:
            proc=subprocess.Popen(cmd,stdin=subprocess.DEVNULL,stdout=out,stderr=err,cwd=temp,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
            try:
                deadline=time.monotonic()+120
                while proc.poll() is None:
                    if cancel.is_set():
                        raise InterruptedError()
                    if time.monotonic()>deadline:
                        raise TimeoutError()
                    if stdout.stat().st_size>65536 or stderr.stat().st_size>65536:
                        raise ValueError('出力が上限を超えたため停止しました。')
                    time.sleep(0.05)
            finally:
                if proc.poll() is None:
                    proc.kill()
                proc.wait()
        if cancel.is_set():
            raise InterruptedError()
        if proc.returncode!=0:
            raise ValueError('ハッシュを計算できませんでした。アクセス権を確認してください。')
        try:
            changed=signature(source)!=before
        except OSError:
            changed=True
        if changed:
            raise ValueError('計算中にファイルが変更されました。変更が止まってから再実行してください。')
        if stdout.stat().st_size>65536:
            raise ValueError('出力が上限を超えました。')
        try:
            digest=stdout.read_bytes().decode('ascii').strip()
        except UnicodeError:
            raise ValueError('計算結果の形式が不正です。') from None
        if re.fullmatch('[0-9a-f]{64}',digest) is None:
            raise ValueError('計算結果の形式が不正です。')
        return digest
