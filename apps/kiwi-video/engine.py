"""Bounded processing of user-selected local media with FFmpeg."""
from pathlib import Path,PurePosixPath
import shutil,ctypes,hashlib,json,math,os,stat,subprocess,sys,tempfile,time,urllib.request,zipfile
from options import validate,filters,output_arguments,output_extension
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

CACHE=windows_folder()/"KiwiVideo"/"FFmpeg-9.0.2-20261025"
EXTENSIONS={".mp4",".m4v",".mov",".mkv",".webm",".avi",".mpg",".mpeg",".ts",".mp3",".m4a",".wav",".flac",".ogg",".opus"}
INPUT=["-protocol_whitelist","file","-format_whitelist","mov,matroska,webm,avi,mpegts,mpeg,mp3,wav,flac,ogg,aac","-threads","2"]
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

def native(name="ffmpeg"):
 pin=json.loads((ROOT/"upstream-pin.json").read_text(encoding="utf8"))
 p=safe_path(CACHE/pin["bin_subdir"]/(name+".exe"))
 if not p.is_file():raise ValueError("先に「動画エンジンを準備」を押してください。")
 return p

def installed():
 pin=json.loads((ROOT/"upstream-pin.json").read_text(encoding="utf8"))
 return (CACHE/pin["bin_subdir"]/"ffmpeg.exe").is_file()

def install(cancel,progress=lambda x:None):
 pin=json.loads((ROOT/"upstream-pin.json").read_text(encoding="utf8"));safe_path(CACHE.parent).mkdir(parents=True,exist_ok=True)
 if CACHE.exists():
  if installed():return CACHE
  raise ValueError("エンジンの保存先に既存ファイルがあります。内容を確認してください。")
 with tempfile.TemporaryDirectory(prefix="kiwi-video-setup-",dir=CACHE.parent) as td:
  work=Path(td);archive=work/"official.zip";total=0;h=hashlib.sha256();deadline=time.monotonic()+600
  req=urllib.request.Request(pin["url"],headers={"User-Agent":"KiwiVideo/0.1"})
  with urllib.request.urlopen(req,timeout=30) as response,archive.open("xb") as dst:
   while chunk:=response.read(512*1024):
    check(cancel);total+=len(chunk)
    if total>pin["size"] or time.monotonic()>deadline:raise ValueError("取得サイズ・時間の上限を超えました。")
    dst.write(chunk);h.update(chunk);progress(f"動画エンジンを取得中 {total/1024**2:.1f} MiB")
  if total!=pin["size"] or h.hexdigest()!=pin["sha256"]:raise ValueError("エンジンの検証に失敗しました。")
  out=work/"files";out.mkdir()
  with zipfile.ZipFile(archive) as z:
   members=[m for m in z.infolist() if not m.is_dir()]
   if len(members)!=len(pin["members"]) or {m.filename for m in members}!=set(pin["members"]):raise ValueError("書庫の内容が一致しません。")
   if sum(m.file_size for m in members)>300*1024**2:raise ValueError("展開サイズが上限を超えました。")
   for m in members:
    check(cancel);q=PurePosixPath(m.filename)
    if q.is_absolute() or '..' in q.parts or '\\' in m.filename or any(':' in s for s in q.parts) or (m.external_attr>>16)&0o170000==0o120000:raise ValueError("書庫に不正なパスがあります。")
    target=out.joinpath(*q.parts);target.parent.mkdir(parents=True,exist_ok=True);data=z.read(m)
    if hashlib.sha256(data).hexdigest()!=pin["members"][m.filename]:raise ValueError("エンジンのファイル検証に失敗しました。")
    with target.open("xb") as f:f.write(data)
  check(cancel);out.rename(CACHE)
 return CACHE

def call(args,work,cancel,name="ffmpeg",timeout=1800,output=None):
 work=Path(work);check(cancel)
 with (work/"stdout.log").open("wb") as out,(work/"stderr.log").open("wb") as err:
  proc=subprocess.Popen([str(native(name)),*args],stdin=subprocess.DEVNULL,stdout=out,stderr=err,cwd=work,creationflags=subprocess.CREATE_NO_WINDOW)
  deadline=time.monotonic()+timeout
  try:
   while proc.poll() is None:
    check(cancel)
    if time.monotonic()>deadline:raise ValueError("処理の時間制限を超えました。")
    if any((work/n).stat().st_size>4*1024**2 for n in ["stdout.log","stderr.log"]):raise ValueError("ログのサイズが上限を超えました。")
    if output and output.exists() and output.stat().st_size>1024**3:raise ValueError("出力が1 GiBを超えました。")
    time.sleep(.1)
  finally:
   if proc.poll() is None:proc.kill()
   proc.wait(timeout=10)
 if any((work/n).stat().st_size>4*1024**2 for n in ["stdout.log","stderr.log"]):raise ValueError("ログのサイズが上限を超えました。")
 if proc.returncode:
  text=(work/"stderr.log").read_bytes()[-3000:].decode("utf8","replace").replace(str(work),"作業フォルダー").replace(str(CACHE),"エンジン")
  raise ValueError("変換できませんでした。形式や区間・切り抜きを確認してください。\n"+text)
 return (work/"stdout.log").read_bytes()

def stage(value,work,cancel):
 p=safe_path(value)
 if not p.is_file() or p.suffix.lower() not in EXTENSIONS or not 0<p.stat().st_size<=2*1024**3:raise ValueError("2 GiB以下の対応する動画・音声ファイルを選んでください。")
 if shutil.disk_usage(work).free<p.stat().st_size+1024**3:raise ValueError("作業用の空き容量が不足しています。")
 dest=work/("input"+p.suffix.lower());count=0
 with p.open("rb") as src,dest.open("xb") as out:
  while chunk:=src.read(1024**2):
   check(cancel);count+=len(chunk)
   if count>2*1024**3:raise ValueError("入力が2 GiBを超えました。")
   out.write(chunk)
 return dest

def probe(path,work,cancel):
 raw=call(["-v","error",*INPUT,"-show_streams","-show_format","-of","json",str(path)],work,cancel,name="ffprobe",timeout=30)
 data=json.loads(raw);streams=data.get("streams",[])
 video=next((s for s in streams if s.get("codec_type")=="video" and not s.get("disposition",{}).get("attached_pic")),None)
 audios=[s for s in streams if s.get("codec_type")=="audio"]
 duration=float(data.get("format",{}).get("duration",0))
 if not math.isfinite(duration) or not 0<duration<=7200:raise ValueError("長さを確認できる2時間以内の動画・音声を選んでください。")
 if video:
  w,h=video.get("width",0),video.get("height",0)
  if min(w,h)<2 or max(w,h)>4096 or w*h>9_000_000:raise ValueError("動画は各辺4,096px・900万画素までです。")
  rate=video.get("avg_frame_rate","0/1").split('/')
  fps=float(rate[0])/float(rate[1]) if len(rate)==2 and float(rate[1]) else 0
  if not 0<fps<=120:raise ValueError("動画は120fpsまでです。")
  high_depth=any(mark in video.get('pix_fmt','') for mark in ['10','12','14','16','48','64']) or video.get('color_transfer') in {'smpte2084','arib-std-b67'}
  rotation=next((float(s.get("rotation",0)) for s in video.get("side_data_list",[]) if "rotation" in s),0)
  if round(abs(rotation))%180==90:w,h=h,w
  video={**video,"display_width":w,"display_height":h,"fps":fps,"high_depth":high_depth}
 return {"video":video,"audios":audios,"duration":duration}

def inspect(value,cancel):
 with tempfile.TemporaryDirectory(prefix="kiwi-video-info-") as td:
  work=Path(td);source=stage(value,work,cancel);return probe(source,work,cancel)

def plan(info,raw):
 v=validate(raw)
 if v["start"]>=info["duration"] or (v["end"] and v["end"]>info["duration"]+.05):raise ValueError("開始・終了をファイルの長さの範囲にしてください。")
 if v["mode"] in {"video","frame"} and not info["video"]:raise ValueError("映像の入ったファイルを選んでください。")
 if v["mode"] in {"video","frame"} and info["video"].get("high_depth"):raise ValueError("HDR・10bit以上の映像変換には対応していません。音声だけの保存は利用できます。")
 if v["mode"]=="audio" and not info["audios"]:raise ValueError("音声がありません。")
 if info["audios"] and v["audio_track"]>=len(info["audios"]):raise ValueError("音声トラック番号を確認してください。")
 if v["crop"] and v["mode"]!="audio":
  video=info["video"]
  if v["x"]+v["width"]>video["display_width"] or v["y"]+v["height"]>video["display_height"]:raise ValueError("切り抜き範囲が映像の外にあります。")
 if info["video"]:v["video_index"]=int(info["video"]["index"])
 return v

def convert(value,raw,directory,cancel,preview=False):
 with tempfile.TemporaryDirectory(prefix="kiwi-video-job-") as td:
  work=Path(td);source=stage(value,work,cancel);info=probe(source,work,cancel);v=plan(info,raw)
  if preview:
   if not info["video"]:raise ValueError("音声のみのファイルはプレビューできません。")
   output=work/"preview.png";vf=filters(v)+["scale=560:315:force_original_aspect_ratio=decrease"]
   args=["-map",f"0:{v['video_index']}","-vf",','.join(vf),"-frames:v","1","-an","-c:v","png"]
  else:
   output=work/("output."+output_extension(v));args=output_arguments(v,bool(info["audios"]))
  prefix=["-hide_banner","-nostdin","-v","error","-n",*INPUT,"-filter_threads","2"]
  if v["start"]:prefix += ["-ss",str(v["start"])]
  call([*prefix,"-i",str(source),*args,str(output)],work,cancel,timeout=60 if preview else 1800,output=output)
  check(cancel)
  if not output.is_file() or not 0<output.stat().st_size<=1024**3:raise ValueError("出力を確認できません。")
  if preview:return output.read_bytes(),info
  folder=safe_path(directory,True);stem=safe_path(value).stem[:90];suffix=output_extension(v)
  for n in range(1000):
   dest=folder/(stem+"_converted"+(f"_{n}" if n else "")+"."+suffix)
   try:
    with dest.open("xb") as dst:
     try:
      with output.open("rb") as src:
       while chunk:=src.read(1024**2):check(cancel);dst.write(chunk)
     except BaseException:
      dst.close();dest.unlink();raise
    return {"output":str(dest),"before":source.stat().st_size,"after":dest.stat().st_size,"duration":info["duration"]}
   except FileExistsError:continue
  raise ValueError("同名ファイルが多すぎます。")
