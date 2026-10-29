"""Create GIFs in a private staging directory and keep originals intact."""
import math,os,re,shutil,stat,subprocess,sys,tempfile,threading,time,warnings
from pathlib import Path
from PIL import Image
from gif_options import validate,build
from gif_frames import normalize_frames
ROOT=Path(sys.executable).parent if getattr(sys,'frozen',False) else Path(__file__).resolve().parent
INPUT_LIMIT=256*1024**2
OUTPUT_LIMIT=256*1024**2
PIXELS=120000000
def check(cancel):
 if cancel.is_set():raise InterruptedError('停止しました。')
def path(value):
 p=Path(os.path.abspath(value))
 for q in [*reversed(p.parents),p]:
  if q.exists() and q.lstat().st_file_attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT:raise ValueError('リンク・ジャンクションは使えません。')
 return p
def gif_info(p,cancel):
 total=duration=count=0
 with warnings.catch_warnings():
  warnings.simplefilter('error',Image.DecompressionBombWarning)
  with Image.open(p) as im:
   if im.format!='GIF':raise ValueError('GIFファイルを選んでください。')
   for i in range(301):
    check(cancel)
    try:im.seek(i)
    except EOFError:break
    count+=1;total+=im.width*im.height
    if count>300 or im.width*im.height>12000000 or total>PIXELS:raise ValueError('GIFは300フレーム・合計1億2,000万画素までです。')
    im.load();duration+=max(10,int(im.info.get('duration',100)))
   return dict(width=im.width,height=im.height,frames=count,duration=duration)
def y4m_info(p,cancel):
 with p.open('rb') as f:
  header=f.readline(2049)
  if len(header)>2048 or not header.startswith(b'YUV4MPEG2 ') or not header.endswith(b'\n'):raise ValueError('Y4Mヘッダーを確認してください。')
  tokens=[t for t in header.split()[1:] if t[:1] in (b'W',b'H',b'F',b'C')]
  if len({t[:1] for t in tokens})!=len(tokens):raise ValueError('Y4Mヘッダーの項目が重複しています。')
  fields={t[:1]:t[1:] for t in tokens}
  try:w=int(fields[b'W']);h=int(fields[b'H']);n,d=map(int,fields[b'F'].split(b':'));rate=n/d
  except (ValueError,KeyError,ZeroDivisionError):raise ValueError('Y4Mのサイズ・FPSを確認してください。')
  chroma=fields.get(b'C',b'420jpeg')
  if not 1<=w<=2048 or not 1<=h<=2048 or not .1<=rate<=1000:raise ValueError('Y4Mは2048×2048px以内の有効なFPSで指定してください。')
  if chroma in (b'420',b'420jpeg',b'420mpeg2',b'420paldv'):size=w*h+2*((w+1)//2)*((h+1)//2)
  elif chroma==b'422':size=w*h+2*((w+1)//2)*h
  elif chroma==b'444':size=w*h*3
  else:raise ValueError('Y4Mは8bitの420・422・444に対応します。白黒・10bit以上には対応しません。')
  count=0;length=p.stat().st_size
  while True:
   check(cancel);line=f.readline(2049)
   if not line:break
   if len(line)>2048 or not re.fullmatch(rb'FRAME(?: [^\r\n]*)?\r?\n',line):raise ValueError('Y4Mフレームを確認してください。')
   count+=1
   if count>300 or count*w*h>PIXELS:raise ValueError('Y4Mは300フレーム・合計1億2,000万画素までです。')
   if f.tell()+size>length:raise ValueError('Y4Mファイルが途中で切れています。')
   f.seek(size,1)
  if not count:raise ValueError('Y4Mにフレームがありません。')
  return dict(width=w,height=h,frames=count,duration=count/rate*1000)
def call(args,stage,cancel,timeout=300):
 check(cancel);native=ROOT/'native/gifski.exe'
 if not native.is_file():raise ValueError('native/gifski.exeが見つかりません。ZIPをすべて展開してください。')
 proc=subprocess.Popen([str(native),*args],stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.PIPE,creationflags=subprocess.CREATE_NO_WINDOW)
 bufs=[bytearray(),bytearray()];threads=[];overflow=threading.Event()
 def read(stream,index):
  try:
   while True:
    b=stream.read(8192)
    if not b:break
    if len(bufs[index])+len(b)>2*1024**2:overflow.set();break
    bufs[index].extend(b)
  except (OSError,ValueError):pass
 for i,s in enumerate([proc.stdout,proc.stderr]):
  t=threading.Thread(target=read,args=(s,i),daemon=True);t.start();threads.append(t)
 deadline=time.monotonic()+timeout;last=0
 try:
  while proc.poll() is None:
   check(cancel)
   if overflow.is_set():raise ValueError('処理ログが2 MiBを超えました。')
   if time.monotonic()>deadline:raise TimeoutError('処理時間の上限（5分）に達しました。')
   if time.monotonic()-last>.2:
    total=0
    for p in stage.rglob('*'):
     if p.is_file():total+=p.stat().st_size
    if total>512*1024**2:raise ValueError('一時ファイルが512 MiBを超えました。')
    out=stage/'output.gif'
    if out.exists() and out.stat().st_size>OUTPUT_LIMIT:raise ValueError('作成GIFが256 MiBを超えました。')
    last=time.monotonic()
   time.sleep(.04)
  for t in threads:t.join(timeout=2)
  if any(t.is_alive() for t in threads) or overflow.is_set():raise ValueError('処理の完了を確認できませんでした。')
  check(cancel);text=b'\n'.join(bufs).decode('utf8',errors='replace')
  if proc.returncode:raise ValueError('GIFを作成できませんでした。入力と設定を確認してください。\n'+text[-2500:])
  return text
 finally:
  if proc.poll() is None:proc.kill()
  proc.wait(timeout=10)
  for s in [proc.stdout,proc.stderr]:s.close()
  for t in threads:t.join(timeout=2)
def cleanup(stage,parent):
 if stage.parent!=parent or stage.resolve().parent!=parent.resolve() or stage.is_symlink() or stage.is_junction() or not stage.name.startswith('.kiwi-gif-'):raise ValueError('一時フォルダーを確認してください。')
 def retry(fn,p,error):
  q=Path(os.path.abspath(p))
  if not q.is_relative_to(stage) or q.is_symlink() or q.is_junction():raise error
  os.chmod(q,stat.S_IWRITE|stat.S_IREAD);fn(p)
 shutil.rmtree(stage,onexc=retry)
def export(values,dest,options,kind,cancel,progress=None):
 o=validate(options,kind);paths=[path(v) for v in values]
 if (kind=='images' and not 2<=len(paths)<=100) or (kind!='images' and len(paths)!=1):raise ValueError('画像は2～100件、GIF・Y4Mは1件を選んでください。')
 total=0;snap={}
 for p in paths:
  check(cancel)
  if not p.is_file():raise ValueError('入力ファイルを確認してください。')
  s=p.stat();total+=s.st_size;snap[p]=(s.st_size,s.st_mtime_ns)
 if total>INPUT_LIMIT:raise ValueError('入力は合計256 MiBまでです。')
 dest=Path(os.path.abspath(dest));parent=path(dest.parent)
 if dest.suffix.lower()!='.gif' or dest.exists() or not parent.is_dir():raise ValueError('新しい.gifファイル名を選んでください。既存ファイルは上書きしません。')
 if kind in ('gif','y4m'):
  info=gif_info(paths[0],cancel) if kind=='gif' else y4m_info(paths[0],cancel)
  if info['duration']/o['speed']>600000:raise ValueError('作成するGIFの長さは10分までです。')
 stage=Path(tempfile.mkdtemp(prefix='.kiwi-gif-',dir=parent));out=stage/'output.gif';started=time.monotonic()
 try:
  if kind=='images':
   if len(paths)/o['fps']*(2 if o['bounce'] else 1)>600:raise ValueError('作成するGIFの長さは10分までです。')
   frames=stage/'frames';frames.mkdir();native_paths,_=normalize_frames([str(p) for p in paths],frames,cancel,o['fit'],o['background'],progress)
  else:native_paths=paths
  call(build(native_paths,out,o,kind),stage,cancel,max(.01,300-(time.monotonic()-started)))
  if not out.is_file() or out.stat().st_size>OUTPUT_LIMIT:raise ValueError('作成GIFを確認できませんでした。')
  result=gif_info(out,cancel)
  if not result['frames'] or result['width']>1600 or result['height']>1600 or result['duration']>600000:raise ValueError('作成GIFがサイズ・長さの上限を超えました。')
  for p,s in snap.items():
   cur=p.stat()
   if (cur.st_size,cur.st_mtime_ns)!=s:raise ValueError('処理中に入力が変更されました。もう一度実行してください。')
  check(cancel);out.rename(dest);result['bytes']=dest.stat().st_size;return result
 finally:cleanup(stage,parent)
