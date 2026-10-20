"""Trace local images into new, validated SVG files."""
import math
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
import warnings
import xml.etree.ElementTree as ET
from PIL import Image, ImageOps
from options import build, validate

ROOT = Path(sys.executable).parent if getattr(sys, 'frozen', False) else Path(__file__).resolve().parent
NS = '{http://www.w3.org/2000/svg}'
OUTPUT_LIMIT = 32 * 1024**2
NUMBER = r'[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?'
TRANSLATE = re.compile(r'translate\(('+NUMBER+r')[ ,]+('+NUMBER+r')\)\Z')
FORMATS = {'PNG','JPEG','WEBP','BMP','TIFF','GIF'}


def check(cancel):
    if cancel.is_set():
        raise InterruptedError('停止しました。')


def safe_path(value, directory=False):
    p = Path(os.path.abspath(value))
    if ':' in str(p)[2:]:
        raise ValueError('通常のファイル・フォルダーを選んでください。')
    for q in [*reversed(p.parents),p]:
        if q.exists() and (q.is_symlink() or getattr(q.lstat(),'st_file_attributes',0) & stat.FILE_ATTRIBUTE_REPARSE_POINT):
            raise ValueError('リンク・ジャンクションは指定できません。')
    if directory and not p.is_dir():
        raise ValueError('保存先フォルダーを確認してください。')
    return p


def load_image(value):
    p = safe_path(value)
    if not p.is_file() or not 0 < p.stat().st_size <= 128*1024**2:
        raise ValueError('空でない128 MiB以下の画像を選んでください。')
    with warnings.catch_warnings():
        warnings.simplefilter('error',Image.DecompressionBombWarning)
        with Image.open(p) as im:
            if im.format not in FORMATS:
                raise ValueError('PNG・JPEG・WebP・BMP・TIFF・GIFに対応します。')
            if im.width*im.height > 8_000_000 or max(im.size) > 8000:
                raise ValueError('画像は800万画素・各辺8,000pxまでです。')
            im.seek(0)
            return ImageOps.exif_transpose(im).convert('RGBA')


def normalized(value, destination, transparent):
    im = load_image(value)
    size = im.size
    alpha = im.getchannel('A')
    white = Image.new('RGBA',size,'white')
    white.alpha_composite(im)
    if transparent and alpha.getextrema()[0] == 0:
        # A transparent border makes VTracer's boundary-based keying deterministic.
        white.putalpha(alpha.point(lambda a: 0 if a == 0 else 255))
        border = Image.new('RGBA',(size[0]+2,size[1]+2),(0,0,0,0))
        border.paste(white,(1,1));border.save(destination)
        return size,1
    white.convert('RGB').save(destination)
    return size,0


def call(args, output, cancel, timeout):
    check(cancel)
    native = ROOT/'native/vtracer.exe'
    if not native.is_file():
        raise ValueError('native/vtracer.exeがありません。ZIP全体を展開してください。')
    proc = subprocess.Popen([str(native),*args],stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.PIPE,
                            creationflags=subprocess.CREATE_NO_WINDOW,env={**os.environ,'RUST_BACKTRACE':'0'})
    buffers = [bytearray(),bytearray()];overflow = threading.Event()
    def read(stream,index):
        try:
            while chunk := stream.read(8192):
                if len(buffers[index])+len(chunk)>1024**2:
                    overflow.set();break
                buffers[index].extend(chunk)
        finally:
            stream.close()
    threads=[threading.Thread(target=read,args=(s,i),daemon=True) for i,s in enumerate((proc.stdout,proc.stderr))]
    for t in threads:t.start()
    deadline=time.monotonic()+timeout
    try:
        while proc.poll() is None:
            check(cancel)
            if overflow.is_set():raise ValueError('処理ログが1 MiBを超えました。')
            if time.monotonic()>deadline:raise TimeoutError('一括処理が5分を超えました。画像を小さくするか、枚数を減らしてください。')
            if output.exists() and output.stat().st_size>OUTPUT_LIMIT:raise ValueError('SVGが32 MiBを超えました。色数や輪郭の細かさを減らしてください。')
            time.sleep(.03)
        for t in threads:t.join(timeout=2)
        check(cancel)
        if overflow.is_set() or any(t.is_alive() for t in threads):raise ValueError('処理結果を確認できませんでした。')
        text=b'\n'.join(buffers).decode('utf8','replace')
        if proc.returncode:raise ValueError('変換できませんでした。\n'+text[-1500:])
    finally:
        if proc.poll() is None:proc.kill()
        proc.wait(timeout=10)
        for t in threads:t.join(timeout=2)


def inspect_svg(path, offset=0, size=None):
    with Path(path).open('rb') as f:raw=f.read(OUTPUT_LIMIT+1)
    if not raw or len(raw)>OUTPUT_LIMIT or b'<!DOCTYPE' in raw.upper() or b'<!ENTITY' in raw.upper():
        raise ValueError('SVGの形式・サイズを確認できませんでした。')
    root=ET.fromstring(raw)
    if root.tag!=NS+'svg' or set(root.attrib)-{'width','height','version'}:
        raise ValueError('対応しないSVG構造です。')
    dimensions=[]
    for key in ['width','height']:
        v=root.get(key,'')
        if not re.fullmatch(r'\d+',v) or not 1<=int(v)<=8002:raise ValueError('SVGの寸法を確認できませんでした。')
        dimensions.append(int(v))
    if size and tuple(dimensions)!=(size[0]+2*offset,size[1]+2*offset):
        raise ValueError('SVGの寸法が入力と一致しません。')
    paths=0
    for child in root:
        paths+=1
        if paths>100000 or child.tag!=NS+'path' or len(child) or set(child.attrib)-{'d','fill','transform'}:
            raise ValueError('SVGのパス構造・件数を確認できませんでした。')
        if not re.fullmatch(r'#[0-9a-fA-F]{6}',child.get('fill','')):
            raise ValueError('SVGに対応しない色指定があります。')
        d=child.get('d','')
        if not d or not re.fullmatch(r'[MLCZmlcz0-9eE.,+\-\s]+',d):
            raise ValueError('SVGに対応しない輪郭指定があります。')
        for number in re.finditer(NUMBER,d):
            if not math.isfinite(float(number[0])):raise ValueError('SVGに不正な座標があります。')
        match=TRANSLATE.fullmatch(child.get('transform',''))
        if not match:raise ValueError('SVGの移動量を確認できませんでした。')
        x,y=map(float,match.groups())
        if not all(math.isfinite(v) for v in (x,y)):raise ValueError('SVGの座標を確認できませんでした。')
        if offset:child.set('transform',f'translate({x-offset:g},{y-offset:g})')
    if size:
        root.set('width',str(size[0]));root.set('height',str(size[1]))
        dimensions=list(size)
    ET.register_namespace('',NS[1:-1])
    clean=ET.tostring(root,encoding='utf8',xml_declaration=True)
    if len(clean)>OUTPUT_LIMIT:raise ValueError('SVGの保存サイズが上限を超えました。')
    return {'width':dimensions[0],'height':dimensions[1],'paths':paths,'bytes':len(clean)},clean


def convert(files, destination, values, cancel, batch=False, progress=lambda text:None):
    started=time.monotonic();o=validate(values)
    if not 1<=len(files)<=20 or (not batch and len(files)!=1):raise ValueError('1枚保存は1ファイル、一括保存は1～20ファイルを指定してください。')
    inputs=[safe_path(f) for f in files]
    if any(not p.is_file() for p in inputs):raise ValueError('画像ファイルを確認してください。')
    if sum(p.stat().st_size for p in inputs)>512*1024**2:raise ValueError('画像の合計は512 MiBまでです。')
    snap={p:(p.stat().st_size,p.stat().st_mtime_ns) for p in inputs}
    dest=safe_path(destination)
    parent=safe_path(dest if batch else dest.parent,directory=True)
    if not batch and (dest.suffix.lower()!='.svg' or dest.exists()):raise ValueError('新しい.svgファイル名を選んでください。既存ファイルは上書きしません。')
    final=parent/('ベクター-'+time.strftime('%Y%m%d-%H%M%S')+'-'+os.urandom(3).hex()) if batch else dest
    stage=Path(tempfile.mkdtemp(prefix='.kiwi-vector-',dir=parent));results=[];total=0
    try:
        outputs=stage/'outputs';outputs.mkdir()
        for index,p in enumerate(inputs,1):
            check(cancel);progress(f'{index}/{len(inputs)}  {p.name}')
            prepared=stage/'input.png'
            size,offset=normalized(p,prepared,o['background']=='original' and o['colormode']=='color')
            out=outputs/(f'{index:03d}-{p.stem[:80]}.svg' if batch else 'result.svg')
            remaining=300-(time.monotonic()-started)
            if remaining<=0:raise TimeoutError('一括処理は5分までです。')
            call(build(prepared,out,o),out,cancel,remaining)
            info,clean=inspect_svg(out,offset,size);out.write_bytes(clean);total+=len(clean)
            if total>128*1024**2:raise ValueError('一括SVGの合計が128 MiBを超えました。')
            results.append({**info,'name':out.name})
        for p,before in snap.items():
            if (p.stat().st_size,p.stat().st_mtime_ns)!=before:raise ValueError('処理中に元画像が変更されました。再度お試しください。')
        check(cancel)
        if batch:outputs.rename(final)
        else:(outputs/'result.svg').rename(final)
        return final,results
    finally:
        shutil.rmtree(stage)
