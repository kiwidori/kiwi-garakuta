"""Bounded local image processing with an explicitly selected raster decoder."""
from pathlib import Path
import ctypes,hashlib,json,os,re,shutil,stat,subprocess,sys,tempfile,threading,time,urllib.request
from options import validate, arguments
ROOT=Path(sys.executable).parent if getattr(sys,"frozen",False) else Path(__file__).resolve().parent
def windows_folder(system=False):
 if os.name != "nt":raise OSError("Windows 11 x64で実行してください。")
 buffer=ctypes.create_unicode_buffer(32768)
 if system:
  length=ctypes.windll.kernel32.GetSystemDirectoryW(buffer,len(buffer))
  if not 0<length<len(buffer):raise OSError("Windowsのシステムフォルダーを取得できません。")
 elif ctypes.windll.shell32.SHGetFolderPathW(None,0x001c,None,0,buffer)!=0:
  raise OSError("ユーザーの保存先を取得できません。")
 return Path(buffer.value)

CACHE=windows_folder() / "KiwiImage" / "ImageMagick-7.1.2-34"
FORMATS={".jpg":"JPEG",".jpeg":"JPEG",".png":"PNG",".webp":"WEBP",".bmp":"BMP",".tif":"TIFF",".tiff":"TIFF",".gif":"GIF",".heic":"HEIC",".heif":"HEIC",".avif":"AVIF"}
EXT={"JPEG":"jpg","PNG":"png","WEBP":"webp","BMP":"bmp","TIFF":"tif","GIF":"gif","ICO":"ico","AVIF":"avif"}
MAX_FILE=50*1024**2
POLICY='''<policymap>
<policy domain="resource" name="memory" value="256MiB"/>
<policy domain="resource" name="map" value="0"/>
<policy domain="resource" name="disk" value="512MiB"/>
<policy domain="resource" name="width" value="8000"/>
<policy domain="resource" name="height" value="8000"/>
<policy domain="resource" name="area" value="25MP"/>
<policy domain="resource" name="list-length" value="2"/>
<policy domain="resource" name="thread" value="2"/>
<policy domain="resource" name="time" value="60"/>
<policy domain="delegate" rights="none" pattern="*"/>
<policy domain="filter" rights="none" pattern="*"/>
<policy domain="path" rights="none" pattern="@*"/>
<policy domain="coder" rights="none" pattern="*"/>
<policy domain="coder" rights="read|write" pattern="{JPEG,JPG,PNG,PNG24,PNG32,WEBP,BMP,BMP3,TIFF,GIF,ICO,HEIC,AVIF}"/>
</policymap>'''

class Cancelled(Exception):pass

def check(cancel):
 if cancel.is_set():raise Cancelled("停止しました。")

def safe_path(value,directory=False):
 p=Path(value).absolute()
 for q in [*reversed(p.parents),p]:
  if q.exists() and (q.is_symlink() or getattr(q.lstat(),"st_file_attributes",0)&stat.FILE_ATTRIBUTE_REPARSE_POINT):
   raise ValueError("リンク・ジャンクションは指定できません。")
 if directory and not p.is_dir():raise ValueError("保存先フォルダーを確認してください。")
 return p

def native():
 p=CACHE/"magick.exe"
 if not p.is_file():raise ValueError("先に「画像エンジンを準備」を押してください。")
 return p

def installed():return (CACHE/"magick.exe").is_file()

def install(cancel,progress=lambda x:None):
 pin=json.loads((ROOT/"upstream-pin.json").read_text(encoding="utf8"))
 safe_path(CACHE.parent).mkdir(parents=True,exist_ok=True)
 if CACHE.exists():
  if installed():return CACHE
  raise ValueError("エンジンの保存先に既存ファイルがあります。内容を確認してください。")
 with tempfile.TemporaryDirectory(prefix="kiwi-image-install-",dir=CACHE.parent) as td:
  tmp=Path(td); archive=tmp/"official.7z";total=0;h=hashlib.sha256()
  req=urllib.request.Request(pin["url"],headers={"User-Agent":"KiwiImage/0.1"})
  deadline=time.monotonic()+120
  with urllib.request.urlopen(req,timeout=30) as response,archive.open("xb") as dst:
   while chunk:=response.read(256*1024):
    check(cancel)
    if time.monotonic()>deadline:raise ValueError("エンジンの取得が時間制限を超えました。")
    total+=len(chunk)
    if total>pin["size"]:raise ValueError("公式ファイルのサイズが一致しません。")
    dst.write(chunk);h.update(chunk);progress(f"画像エンジンを取得中 {total//1024:,} KiB")
  if total!=pin["size"] or h.hexdigest()!=pin["sha256"]:raise ValueError("公式ファイルの検証に失敗しました。")
  tar=windows_folder(system=True)/"tar.exe"
  listing=subprocess.run([str(tar),"-tf",str(archive)],capture_output=True,timeout=30,creationflags=subprocess.CREATE_NO_WINDOW,check=True).stdout.decode("utf8").splitlines()
  if sorted(listing)!=sorted(pin["members"]):raise ValueError("書庫の内容が一致しません。")
  out=tmp/"files";out.mkdir()
  subprocess.run([str(tar),"-xf",str(archive),"-C",str(out)],capture_output=True,timeout=30,creationflags=subprocess.CREATE_NO_WINDOW,check=True)
  for name,digest in pin["members"].items():
   p=out/name
   if p.is_symlink() or not p.is_file() or hashlib.sha256(p.read_bytes()).hexdigest()!=digest:raise ValueError("エンジンの内容検証に失敗しました。")
  check(cancel);out.rename(CACHE)
 return CACHE

def call(args,work,cancel,timeout=65,output=None):
 check(cancel);work=Path(work)
 (work/"policy.xml").write_text(POLICY,encoding="utf8")
 env={**os.environ,"MAGICK_CONFIGURE_PATH":str(work),"MAGICK_TEMPORARY_PATH":str(work),"MAGICK_HOME":str(CACHE),"OMP_NUM_THREADS":"2","MAGICK_THREAD_LIMIT":"2"}
 for k in ["MAGICK_CODER_MODULE_PATH","MAGICK_FILTER_MODULE_PATH","MAGICK_FONT_PATH"]:env.pop(k,None)
 with (work/"stdout.log").open("wb") as out,(work/"stderr.log").open("wb") as err:
  proc=subprocess.Popen([str(native()),*args],stdin=subprocess.DEVNULL,stdout=out,stderr=err,cwd=work,env=env,creationflags=subprocess.CREATE_NO_WINDOW)
  deadline=time.monotonic()+timeout
  try:
   while proc.poll() is None:
    check(cancel)
    if time.monotonic()>deadline:raise ValueError("画像処理が時間制限を超えました。")
    if (work/"stdout.log").stat().st_size>1024**2 or (work/"stderr.log").stat().st_size>1024**2:raise ValueError("エンジンのログが上限を超えました。")
    if output and Path(output).exists() and Path(output).stat().st_size>128*1024**2:raise ValueError("出力が128 MiBを超えました。")
    time.sleep(.05)
  finally:
   if proc.poll() is None:proc.kill()
   proc.wait(timeout=10)
 error=(work/"stderr.log").read_bytes()[:8192].decode("utf8","replace")
 if proc.returncode:raise ValueError("画像処理に失敗しました。入力形式や設定を確認してください。\n"+error.replace(str(work),"作業フォルダー").replace(str(CACHE),"エンジン")[:1200])
 return (work/"stdout.log").read_bytes()[:8192].decode("utf8","replace")

def stage_input(value,work,cancel):
 p=safe_path(value)
 if p.suffix.lower() not in FORMATS:raise ValueError("対応する画像ファイルを選んでください。")
 if not p.is_file() or not 0<p.stat().st_size<=MAX_FILE:raise ValueError("入力は1枚50 MiBまでです。")
 target=work/("input"+p.suffix.lower());total=0
 with p.open("rb") as src,target.open("xb") as dst:
  while chunk:=src.read(256*1024):
   check(cancel);total+=len(chunk)
   if total>MAX_FILE:raise ValueError("入力は1枚50 MiBまでです。")
   dst.write(chunk)
 coded=FORMATS[p.suffix.lower()]+":"+str(target)+"[0]"
 info=call(["identify","-ping","-format","%w %h %[orientation]",coded],work,cancel)
 if not re.fullmatch(r"\d+ \d+ [A-Za-z]+",info.strip()):raise ValueError("画像の寸法を読み取れません。")
 parts=info.split();w,h=map(int,parts[:2])
 if parts[2] in {"LeftTop","RightTop","RightBottom","LeftBottom"}:w,h=h,w
 if min(w,h)<1 or max(w,h)>8000 or w*h>25_000_000:raise ValueError("画像は2,500万画素・各辺8,000pxまでです。")
 return coded,(w,h)

def transform(value,raw,cancel,preview=False):
 opts=validate(raw)
 with tempfile.TemporaryDirectory(prefix="kiwi-image-job-") as td:
  work=Path(td);source,size=stage_input(value,work,cancel)
  # The output is checked again after rotation and EXIF orientation by the native policy.
  if opts["crop_enabled"] and (opts["x"]+opts["crop_width"]>size[0] or opts["y"]+opts["crop_height"]>size[1]):
   raise ValueError("切り抜き範囲が画像の外にあります。")
  w,h=(opts["crop_width"],opts["crop_height"]) if opts["crop_enabled"] else size
  mode=opts["size_mode"]
  if mode in {"fit","fill","exact"}:
   if mode=="fit":
    ratio=min(opts["width"]/w,opts["height"]/h)
    if not opts["upscale"]:ratio=min(1,ratio)
    w,h=max(1,round(w*ratio)),max(1,round(h*ratio))
   else:
    if mode=="exact" and not opts["upscale"] and (opts["width"]>w or opts["height"]>h):raise ValueError("元画像より大きくするには拡大を許可してください。")
    w,h=opts["width"],opts["height"]
  elif mode=="percent":
   if opts["percent"]>100 and not opts["upscale"]:raise ValueError("100%より大きくするには拡大を許可してください。")
   w,h=max(1,round(w*opts["percent"]/100)),max(1,round(h*opts["percent"]/100))
  if max(w,h)>8000 or w*h>25_000_000:raise ValueError("出力は2,500万画素・各辺8,000pxまでです。")
  fmt=opts["format"]
  output=work/("output."+EXT[fmt])
  extra=["-resize","256x256>"] if fmt=="ICO" else []
  coder="PNG32" if fmt=="PNG" else fmt
  call([source,*arguments(opts),*extra,coder+":"+str(output)],work,cancel,output=output)
  if not output.is_file() or not 0<output.stat().st_size<=128*1024**2:raise ValueError("画像出力を確認できません。")
  if preview:
   thumb=work/"preview.png"
   call([coder+":"+str(output)+"[0]","-thumbnail","640x400>","PNG32:"+str(thumb)],work,cancel,output=thumb)
   output=thumb
  check(cancel);return output.read_bytes()

def batch(values,raw,directory,cancel,progress=lambda x:None):
 opts=validate(raw);paths=[safe_path(x) for x in values]
 if not 1<=len(paths)<=20:raise ValueError("画像は1～20枚選んでください。")
 if sum(p.stat().st_size for p in paths)>200*1024**2:raise ValueError("入力の合計は200 MiBまでです。")
 directory=safe_path(directory,True);results=[];start=time.monotonic();total=0
 for i,p in enumerate(paths):
  check(cancel)
  if time.monotonic()-start>600:raise ValueError("一括処理が10分を超えました。保存済みファイルは残ります。")
  data=transform(p,opts,cancel);total+=len(data)
  if total>512*1024**2:raise ValueError("出力合計が512 MiBを超えました。")
  suffix="_converted."+EXT[opts["format"]];base=p.stem[:100];dest=directory/(base+suffix)
  for n in range(1000):
   candidate=dest if n==0 else directory/(base+f"_converted_{n}."+EXT[opts["format"]])
   try:
    with candidate.open("xb") as f:
     try:f.write(data)
     except BaseException:
      f.close();candidate.unlink();raise
    break
   except FileExistsError:continue
  else:raise ValueError("保存先の同名ファイルが多すぎます。")
  item={"input":p.name,"output":str(candidate),"before":p.stat().st_size,"after":len(data)}
  results.append(item);progress(item)
 return results
