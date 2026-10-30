"""Optimize a temporary PNG copy and create a new destination exclusively."""
import os
import sys
import time
import shutil
import tempfile
import subprocess
from pathlib import Path

def resource_dir():
    return Path(sys._MEIPASS) if getattr(sys,'frozen',False) else Path(__file__).resolve().parent

def validate_png(data):
    if len(data)>20*1024*1024 or data[:8]!=b'\x89PNG\r\n\x1a\n':
        raise ValueError('20 MiB以下のPNGファイルを選んでください。')
    offset=8
    first=True
    ended=False
    while offset+12<=len(data):
        size=int.from_bytes(data[offset:offset+4],'big')
        kind=data[offset+4:offset+8]
        if offset+size+12>len(data):
            raise ValueError('PNGのデータが不完全です。')
        if first:
            if kind!=b'IHDR' or size!=13:
                raise ValueError('PNGのヘッダーが不正です。')
            w=int.from_bytes(data[offset+8:offset+12],'big')
            h=int.from_bytes(data[offset+12:offset+16],'big')
            if not w or not h or w*h>16_000_000:
                raise ValueError('1600万画素以下のPNGを選んでください。')
            first=False
        if kind==b'acTL':
            raise ValueError('アニメーションPNGは対象外です。')
        offset+=size+12
        if kind==b'IEND':
            ended=True
            break
    if first or not ended:
        raise ValueError('PNGのデータが不完全です。')

def optimize(exe,source,destination,level,cancel):
    source=Path(source).resolve()
    destination=Path(destination).resolve()
    if not source.is_file() or source.suffix.lower()!='.png':
        raise ValueError('入力PNGを選んでください。')
    if source==destination or destination.exists() or not destination.parent.is_dir() or destination.suffix.lower()!='.png':
        raise ValueError('既存ファイルと異なる、新しいPNG保存先を選んでください。')
    if level not in range(5):
        raise ValueError('圧縮レベルは0〜4です。')
    if not exe.is_file():
        raise ValueError('同梱のoxipng.exeが見つかりません。')
    with source.open('rb') as stream:
        data=stream.read(20*1024*1024+1)
    validate_png(data)
    if cancel.is_set():
        raise InterruptedError()
    with tempfile.TemporaryDirectory(prefix='kiwi-png-') as temp:
        folder=Path(temp)
        input_path=folder/'input.png'
        output=folder/'optimized.png'
        log=folder/'log.bin'
        input_path.write_bytes(data)
        cmd=[str(exe.resolve()),'-o',str(level),'--threads','2','--timeout','115','--force','--out',str(output),str(input_path)]
        with log.open('wb') as err:
            proc=subprocess.Popen(cmd,stdin=subprocess.DEVNULL,stdout=err,stderr=err,cwd=temp,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
            try:
                deadline=time.monotonic()+120
                while proc.poll() is None:
                    if cancel.is_set():
                        raise InterruptedError()
                    if time.monotonic()>deadline:
                        raise TimeoutError()
                    if log.stat().st_size>65536 or (output.exists() and output.stat().st_size>24*1024*1024):
                        raise ValueError('処理結果が上限を超えたため停止しました。')
                    time.sleep(0.05)
            finally:
                if proc.poll() is None:
                    proc.kill()
                proc.wait()
        if cancel.is_set():
            raise InterruptedError()
        if proc.returncode!=0 or not output.is_file():
            raise ValueError('圧縮に失敗しました。PNGの内容を確認してください。')
        if output.stat().st_size>24*1024*1024:
            raise ValueError('処理結果が上限を超えました。')
        chosen=output if output.stat().st_size<len(data) else input_path
        after=chosen.stat().st_size
        # Exclusive creation also protects against a save-path race.
        try:
            target=destination.open('xb')
        except FileExistsError:
            raise ValueError('保存先が既に存在します。別の名前を選んでください。') from None
        try:
            with target,chosen.open('rb') as stream:
                shutil.copyfileobj(stream,target)
        except Exception:
            destination.unlink(missing_ok=True)
            raise
        return {'before':len(data),'after':after,'saved_percent':100*(len(data)-after)/len(data)}
