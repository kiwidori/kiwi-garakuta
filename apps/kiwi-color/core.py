"""Fixed-command, bounded pastel color conversion."""
import sys
import re
import time
import tempfile
import subprocess
from pathlib import Path

def resource_dir():
    return Path(sys._MEIPASS) if getattr(sys,'frozen',False) else Path(__file__).resolve().parent

def validate_input(value):
    value=value.strip()
    if not value or len(value)>128 or any(ord(c)<32 or ord(c)==127 for c in value):
        raise ValueError('色を128文字以内で1行に入力してください。')
    if value.lower()=='transparent' or re.fullmatch('#?[0-9a-fA-F]{8}',value):
        raise ValueError('透明度付きの色は対象外です。')
    if re.fullmatch('#?[0-9a-fA-F]{3}(?:[0-9a-fA-F]{3})?',value):
        return value
    if re.fullmatch('[a-zA-Z]+',value):
        return value
    if re.fullmatch(r'(?:rgb|hsl)\([0-9.,% +\-]+\)',value,re.IGNORECASE):
        return value
    raise ValueError('HEX・RGB・HSL、または英語の色名を入力してください。')

def convert_color(exe,value,cancel):
    value=validate_input(value)
    if not exe.is_file():
        raise ValueError('同梱のpastel.exeが見つかりません。')
    if cancel.is_set():
        raise InterruptedError()
    result={}
    deadline=time.monotonic()+15
    with tempfile.TemporaryDirectory(prefix='kiwi-color-') as temp:
        folder=Path(temp)
        for fmt in ('hex','rgb','hsl'):
            if cancel.is_set():
                raise InterruptedError()
            stdout=folder/f'{fmt}.txt'
            stderr=folder/f'{fmt}-error.txt'
            source=value if fmt=='hex' else result['hex']
            cmd=[str(exe.resolve()),'--color-mode','off','format',fmt,'--',source]
            with stdout.open('wb') as out,stderr.open('wb') as err:
                proc=subprocess.Popen(cmd,stdin=subprocess.DEVNULL,stdout=out,stderr=err,cwd=temp,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
                try:
                    while proc.poll() is None:
                        if cancel.is_set():
                            raise InterruptedError()
                        if time.monotonic()>deadline:
                            raise TimeoutError()
                        if max(stdout.stat().st_size,stderr.stat().st_size)>4096:
                            raise ValueError('出力が上限を超えたため停止しました。')
                        time.sleep(0.05)
                finally:
                    if proc.poll() is None:
                        proc.kill()
                    proc.wait()
            if cancel.is_set():
                raise InterruptedError()
            if proc.returncode!=0:
                raise ValueError('色を読み取れませんでした。対応する表記で入力してください。')
            if stdout.stat().st_size>4096:
                raise ValueError('出力が上限を超えました。')
            try:
                text=stdout.read_bytes().decode('ascii').strip()
            except UnicodeError:
                raise ValueError('変換結果の形式が不正です。') from None
            pattern={'hex':'#[0-9a-f]{6}','rgb':r'rgb\([0-9., ]+\)','hsl':r'hsl\([0-9.,% ]+\)'}[fmt]
            if not re.fullmatch(pattern,text):
                raise ValueError('変換結果の形式が不正です。')
            result[fmt]=text
    return result
