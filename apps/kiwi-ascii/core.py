"""Bounded offline image conversion using the bundled upstream executable."""
import math
import subprocess
import sys
import tempfile
import time
import warnings
from pathlib import Path
from PIL import Image

LIMIT=20*1024*1024
EXTENSIONS={'.png','.jpg','.jpeg','.bmp','.webp','.tif','.tiff'}
FORMATS={'PNG','JPEG','BMP','WEBP','TIFF'}

def resource_dir():
    return Path(sys._MEIPASS) if getattr(sys,'frozen',False) else Path(__file__).resolve().parent

def validate_image(path,width):
    if isinstance(width,bool) or not isinstance(width,int) or not 20<=width<=160:
        raise ValueError('横幅は20〜160文字で指定してください。')
    path=Path(path)
    if path.suffix.lower() not in EXTENSIONS or not path.is_file():
        raise ValueError('対応するローカル画像ファイルを選んでください。')
    if not 0<path.stat().st_size<=LIMIT:
        raise ValueError('画像ファイルは20MiB以下にしてください。')
    try:
        with warnings.catch_warnings():
            warnings.simplefilter('error',Image.DecompressionBombWarning)
            with Image.open(path) as image:
                if image.format not in FORMATS or getattr(image,'n_frames',1)!=1:
                    raise ValueError('対応する静止画像を選んでください。')
                w,h=image.size
                if not w or not h or w*h>20_000_000:
                    raise ValueError('画像は2,000万画素以下にしてください。')
                if math.ceil(width*h/w/2)>400:
                    raise ValueError('画像が縦長すぎます。横幅を減らすか別の画像を選んでください。')
                image.verify()
    except ValueError:
        raise
    except Exception:
        raise ValueError('画像を読み取れませんでした。') from None
    return path.resolve()

def convert_image(exe,path,width,negative,braille,cancel):
    path=validate_image(path,width)
    exe=Path(exe).resolve()
    if not exe.is_file():
        raise ValueError('同梱の変換エンジンが見つかりません。')
    if cancel.is_set():
        raise InterruptedError()
    with tempfile.TemporaryDirectory(prefix='kiwi-ascii-') as temp:
        temp=Path(temp)
        local=temp/('input'+path.suffix.lower())
        # Bounded snapshot: a changing input cannot become an unbounded read.
        with path.open('rb') as source,local.open('wb') as dest:
            dest.write(source.read(LIMIT+1))
        validate_image(local,width)
        outpath,errpath=temp/'result.txt',temp/'error.txt'
        command=[str(exe),'--width',str(width)]
        if negative:
            command.append('--negative')
        if braille:
            command.extend(['--braille','--dither'])
        command.extend(['--',str(local)])
        deadline=time.monotonic()+30
        with outpath.open('wb') as out,errpath.open('wb') as err:
            proc=subprocess.Popen(command,stdin=subprocess.DEVNULL,stdout=out,stderr=err,cwd=temp,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
            try:
                while proc.poll() is None:
                    if cancel.is_set():
                        raise InterruptedError()
                    if time.monotonic()>deadline:
                        raise TimeoutError()
                    if max(outpath.stat().st_size,errpath.stat().st_size)>1024*1024:
                        raise ValueError('出力が上限を超えたため停止しました。')
                    time.sleep(0.05)
            finally:
                if proc.poll() is None:
                    proc.kill()
                proc.wait()
        if cancel.is_set():
            raise InterruptedError()
        if proc.returncode or outpath.stat().st_size>1024*1024:
            raise ValueError('変換できませんでした。別の画像をお試しください。')
        try:
            result=outpath.read_bytes().decode('utf-8').replace('\r\n','\n')
        except UnicodeError:
            raise ValueError('変換結果の形式が不正です。') from None
        if not result.strip() or any(ord(c)<32 and c not in '\n\t' for c in result):
            raise ValueError('変換結果の形式が不正です。')
        return result
