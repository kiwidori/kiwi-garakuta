"""Read drive capacity snapshots from the pinned duf executable."""
import csv
import io
import json
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path

def resource_dir():
    return Path(sys._MEIPASS) if getattr(sys,'frozen',False) else Path(__file__).resolve().parent

def parse_drives(raw):
    try:
        payload=json.loads(raw)
    except (ValueError,UnicodeError):
        raise ValueError('容量情報の形式が不正です。') from None
    if not isinstance(payload,list) or len(payload)>256:
        raise ValueError('容量情報の形式が不正です。')
    rows=[]
    seen=set()
    for item in payload:
        if not isinstance(item,dict):
            raise ValueError('容量情報の形式が不正です。')
        drive=item.get('mount_point','')
        if item.get('device_type')!='local' or not isinstance(drive,str) or not re.fullmatch(r'[a-zA-Z]:\\',drive):
            continue
        drive=drive.upper()
        total,used,free=(item.get(key) for key in ('total','used','free'))
        if any(type(x) is not int or not 0<=x<2**63 for x in (total,used,free)) or used>total or free>total:
            raise ValueError('容量情報の数値が不正です。')
        if not total or drive in seen:
            continue
        seen.add(drive)
        fs=item.get('fs_type','')
        # No volume labels, filesystem paths or device names enter the GUI/CSV.
        fs=fs if fs in ('NTFS','FAT','FAT32','exFAT','ReFS','CDFS','UDF') else '不明'
        rows.append({'drive':drive,'filesystem':fs,'total':total,'used':used,'free':free,'usage':used/total*100})
    if not rows:
        raise ValueError('読み取れるドライブがありません。')
    return sorted(rows,key=lambda row:row['drive'])

def read_drives(exe,cancel):
    exe=Path(exe).resolve()
    if not exe.is_file():
        raise ValueError('同梱のduf.exeが見つかりません。')
    if cancel.is_set():
        raise InterruptedError()
    with tempfile.TemporaryDirectory(prefix='kiwi-space-') as temp:
        outpath,errpath=Path(temp)/'out.json',Path(temp)/'error.txt'
        deadline=time.monotonic()+15
        with outpath.open('wb') as out,errpath.open('wb') as err:
            proc=subprocess.Popen([str(exe),'--json','--only','local'],stdin=subprocess.DEVNULL,stdout=out,stderr=err,cwd=temp,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
            try:
                while proc.poll() is None:
                    if cancel.is_set():
                        raise InterruptedError()
                    if time.monotonic()>deadline:
                        raise TimeoutError()
                    if max(outpath.stat().st_size,errpath.stat().st_size)>1024*1024:
                        raise ValueError('容量情報が出力の上限を超えました。')
                    time.sleep(0.05)
            finally:
                if proc.poll() is None:
                    proc.kill()
                proc.wait()
        if cancel.is_set():
            raise InterruptedError()
        if proc.returncode or outpath.stat().st_size>1024*1024:
            raise ValueError('容量情報を取得できませんでした。')
        return parse_drives(outpath.read_bytes())

def format_size(size):
    unit,divisor=('TiB',1024**4) if size>=1024**4 else ('GiB',1024**3)
    return f'{size/divisor:,.1f} {unit}'

def csv_bytes(rows):
    output=io.StringIO(newline='')
    writer=csv.writer(output,lineterminator='\r\n')
    writer.writerow(['drive','filesystem','total_bytes','used_bytes','free_bytes','usage_percent'])
    for row in rows:
        writer.writerow([row['drive'],row['filesystem'],row['total'],row['used'],row['free'],f"{row['usage']:.2f}"])
    return output.getvalue().encode('utf-8-sig')
