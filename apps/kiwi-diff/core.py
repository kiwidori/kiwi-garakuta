"""Bounded, read-only UTF-8 file comparison with difftastic."""
import os
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path
LIMIT=2*1024*1024

def display_segments(raw):
    segments=[]
    cursor=0
    style=''
    for match in re.finditer(r'\x1b\[([0-9;]*)m',raw):
        if match.start()>cursor:
            segments.append((raw[cursor:match.start()],style))
        for parameter in (int(x or '0') for x in match[1].split(';')):
            if parameter in (0,39):
                style=''
            elif parameter in (31,91):
                style='removed'
            elif parameter in (32,92):
                style='added'
            elif 30<=parameter<=37 or 90<=parameter<=97:
                style=''
        cursor=match.end()
    if cursor<len(raw):
        segments.append((raw[cursor:],style))
    return segments

def resource_dir():
    return Path(sys._MEIPASS) if getattr(sys,'frozen',False) else Path(__file__).resolve().parent

def snapshot(source,dest):
    source=Path(source)
    if not source.is_file() or source.stat().st_size>LIMIT:
        raise ValueError('2MiB以下のテキストファイルを選んでください。')
    with source.open('rb') as stream:
        data=stream.read(LIMIT+1)
    if len(data)>LIMIT:
        raise ValueError('ファイルが2MiBを超えています。')
    try:
        text=data.decode('utf-8-sig')
    except UnicodeError:
        raise ValueError('UTF-8形式のテキストファイルを選んでください。') from None
    if any(ord(c)<32 and c not in '\t\r\n' for c in text):
        raise ValueError('バイナリや制御文字を含むファイルは比較できません。')
    suffix=source.suffix.lower()
    suffix=suffix if re.fullmatch(r'\.[a-z0-9_-]{1,20}',suffix) else '.txt'
    target=dest.with_suffix(suffix)
    target.write_bytes(text.encode('utf-8'))
    return target

def compare_files(exe,left,right,plain,cancel):
    exe=Path(exe).resolve()
    if not exe.is_file():
        raise ValueError('同梱のdifft.exeが見つかりません。')
    if cancel.is_set():
        raise InterruptedError()
    with tempfile.TemporaryDirectory(prefix='kiwi-diff-') as temp:
        folder=Path(temp)
        old=snapshot(left,folder/'old')
        new=snapshot(right,folder/'new')
        command=[str(exe),'--color','always','--syntax-highlight','off','--display','inline','--width','100','--exit-code','--strip-cr','on','--graph-limit','500000','--byte-limit','1000000']
        if plain:
            command.extend(['--override','*:text'])
        command.extend(['--',old.name,new.name])
        env={k:v for k,v in os.environ.items() if not k.startswith('DFT_')}
        outpath,errpath=folder/'result.txt',folder/'error.txt'
        deadline=time.monotonic()+20
        with outpath.open('wb') as out,errpath.open('wb') as err:
            proc=subprocess.Popen(command,stdin=subprocess.DEVNULL,stdout=out,stderr=err,cwd=folder,env=env,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
            try:
                while proc.poll() is None:
                    if cancel.is_set():
                        raise InterruptedError()
                    if time.monotonic()>deadline:
                        raise TimeoutError()
                    if max(outpath.stat().st_size,errpath.stat().st_size)>LIMIT:
                        raise ValueError('差分が2MiBの出力上限を超えました。')
                    time.sleep(0.05)
            finally:
                if proc.poll() is None:
                    proc.kill()
                proc.wait()
        if cancel.is_set():
            raise InterruptedError()
        if proc.returncode not in (0,1) or outpath.stat().st_size>LIMIT:
            raise ValueError('比較できませんでした。別のファイルをお試しください。')
        try:
            result=outpath.read_bytes().decode('utf-8').replace('\r\n','\n')
        except UnicodeError:
            raise ValueError('比較結果の形式が不正です。') from None
        segments=display_segments(result)
        result=''.join(text for text,_ in segments)
        if not result.strip() or any(ord(c)<32 and c not in '\t\n' for c in result):
            raise ValueError('比較結果の形式が不正です。')
        return {'text':result,'changed':proc.returncode==1,'segments':segments}
