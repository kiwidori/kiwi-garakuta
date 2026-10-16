"""Bounded local archive operations with separate output directories."""
import ctypes,json,os,re,shutil,stat,subprocess,sys,tempfile,threading,time,zipfile,tarfile
from pathlib import Path,PureWindowsPath
from cli_options import build_args
ROOT=Path(sys.executable).parent if getattr(sys,'frozen',False) else Path(__file__).resolve().parent
LIMIT=2*1024**3
COUNT=10000
class ArchiveError(ValueError):pass

def check_cancel(cancel):
 if cancel.is_set():raise InterruptedError('停止しました。')

def reparse(p):
 s=p.lstat();return bool(s.st_file_attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT)

def safe_path(p):
 p=Path(os.path.abspath(p))
 for part in [*reversed(p.parents),p]:
  if part.exists() and reparse(part):raise ArchiveError('リンク・ジャンクションは対象にできません。')
 return p

def scan(root,cancel,limit=LIMIT,count=COUNT):
 total=0;seen=0;stack=[root]
 while stack:
  check_cancel(cancel);p=stack.pop();s=p.lstat()
  if s.st_file_attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT:raise ArchiveError('リンク・ジャンクションは対象にできません。')
  seen+=1
  if seen>count:raise ArchiveError('項目数の上限（10,000件）を超えました。')
  if stat.S_ISDIR(s.st_mode):
   with os.scandir(p) as entries:stack.extend(Path(e.path) for e in entries)
  elif stat.S_ISREG(s.st_mode):
   total+=s.st_size
   if total>limit:raise ArchiveError('サイズの上限（2 GiB）を超えました。')
  else:raise ArchiveError('通常のファイル・フォルダーだけを選んでください。')
 return total,seen

def inputs(paths,cancel,folders=False):
 if not 1<=len(paths)<=32:raise ArchiveError('対象は1～32件で指定してください。')
 out=[];total=count=0;names=set()
 for value in paths:
  check_cancel(cancel);p=safe_path(value)
  if not p.exists() or (not folders and not p.is_file()):raise ArchiveError('対象ファイルを確認してください。')
  if folders and p.name.casefold() in names:raise ArchiveError('同名の対象があります。名前の違うファイル・フォルダーを選んでください。')
  names.add(p.name.casefold());size,n=scan(p,cancel);total+=size;count+=n
  if total>LIMIT or count>COUNT:raise ArchiveError('合計2 GiB・10,000項目までです。')
  out.append(p)
 return out

def entry_name(name):
 name=name.replace('\\','/');p=PureWindowsPath(name)
 if not name or p.is_absolute() or p.drive or name.startswith('/') or any(x in ('..','') for x in name.rstrip('/').split('/')):raise ArchiveError('展開できないパスを含む書庫です。')
 reserved={'CON','PRN','AUX','NUL','CONIN$','CONOUT$',*[f'COM{i}' for i in range(1,10)],*[f'LPT{i}' for i in range(1,10)]}
 parts=[x for x in name.rstrip('/').split('/') if x!='.']
 for part in parts:
  if any(ord(c)<32 or c in ':<>"|?*' for c in part) or part.endswith((' ','.')) or part.split('.')[0].upper() in reserved:raise ArchiveError('Windowsで扱えない名前を含む書庫です。')
 return '/'.join(parts).casefold()

def preflight(path,cancel):
 seen=set();total=count=0
 def check(name,size,isdir,link):
  nonlocal total,count
  check_cancel(cancel);key=entry_name(name)
  if link:raise ArchiveError('リンクを含む書庫は展開できません。')
  if key in seen:raise ArchiveError('同じ名前の項目を含む書庫は展開できません。')
  seen.add(key);total+=size;count+=1
  if total>LIMIT or count>COUNT:raise ArchiveError('展開後は2 GiB・10,000項目までです。')
 if zipfile.is_zipfile(path):
  with zipfile.ZipFile(path) as z:
   for i in z.infolist():check(i.filename,i.file_size,i.is_dir(),stat.S_IFMT(i.external_attr>>16)==stat.S_IFLNK)
  return
 try:t=tarfile.open(path,'r:*')
 except tarfile.ReadError:return
 with t:
  for i in t:check(i.name,i.size,i.isdir(),not(i.isfile() or i.isdir()))

def no_streams(path):
 class DATA(ctypes.Structure):_fields_=[('size',ctypes.c_longlong),('name',ctypes.c_wchar*296)]
 kernel=ctypes.WinDLL('kernel32',use_last_error=True);first=kernel.FindFirstStreamW
 first.argtypes=[ctypes.c_wchar_p,ctypes.c_int,ctypes.POINTER(DATA),ctypes.c_ulong];first.restype=ctypes.c_void_p
 nxt=kernel.FindNextStreamW;nxt.argtypes=[ctypes.c_void_p,ctypes.POINTER(DATA)];nxt.restype=ctypes.c_int
 close=kernel.FindClose;close.argtypes=[ctypes.c_void_p];close.restype=ctypes.c_int
 d=DATA();h=first(str(path),0,ctypes.byref(d),0)
 if h==ctypes.c_void_p(-1).value:
  if ctypes.get_last_error() in (38,1,50):return
  raise ArchiveError('展開ファイルを確認できませんでした。')
 try:
  while True:
   if d.name not in ('::$DATA',''):raise ArchiveError('代替データストリームを含む書庫は展開できません。')
   if not nxt(h,ctypes.byref(d)):
    if ctypes.get_last_error()!=38:raise ArchiveError('展開ファイルを確認できませんでした。')
    break
 finally:close(h)

def verify_tree(root,cancel):
 scan(root,cancel);no_streams(root)
 for base,dirs,files in os.walk(root,followlinks=False):
  check_cancel(cancel)
  for name in [*dirs,*files]:
   p=Path(base)/name;entry_name(str(p.relative_to(root)))
   if reparse(p) or p.stat().st_nlink>1:raise ArchiveError('リンクを含む展開結果は保存できません。')
   no_streams(p)

def cleanup(stage,parent):
 stage=Path(stage);parent=Path(parent)
 if stage.parent!=parent or stage.resolve().parent!=parent.resolve() or reparse(stage) or not stage.name.startswith('.kiwi-archive-'):raise ArchiveError('一時フォルダーを確認してください。')
 def retry(function,path,error):
  p=Path(os.path.abspath(path))
  if not p.is_relative_to(stage) or p.is_symlink() or p.is_junction():raise error
  os.chmod(p,stat.S_IWRITE|stat.S_IREAD);function(path)
 shutil.rmtree(stage,onexc=retry)

def call(args,cancel,password='',watch=None,timeout=300):
 check_cancel(cancel)
 if len(password.encode('utf8'))>1024 or '\x00' in password:raise ArchiveError('パスワードはUTF-8で1,024バイト以内にしてください。')
 native=ROOT/'native/ouch.exe'
 if not native.is_file():raise ArchiveError('native/ouch.exeが見つかりません。ZIPをすべて展開してください。')
 env=os.environ.copy()
 for k in list(env):
  if k.startswith('OUCH_') or k in ('ACCESSIBLE','CLICOLOR_FORCE'):env.pop(k)
 env.update(NO_COLOR='1',OUCH_MAX_DECOMPRESSED_BYTES=str(LIMIT+1))
 if password:env['OUCH_PASSWORD']=password
 proc=subprocess.Popen([str(native),*args],stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.PIPE,env=env,creationflags=subprocess.CREATE_NO_WINDOW)
 bufs=[bytearray(),bytearray()];overflow=threading.Event();threads=[]
 def read(s,i):
  try:
   while True:
    b=s.read(8192)
    if not b:break
    if len(bufs[i])+len(b)>4*1024*1024:overflow.set();break
    bufs[i].extend(b)
  except (OSError,ValueError):pass
 for i,s in enumerate([proc.stdout,proc.stderr]):
  t=threading.Thread(target=read,args=(s,i),daemon=True);t.start();threads.append(t)
 deadline=time.monotonic()+timeout;last=0
 try:
  while proc.poll() is None:
   check_cancel(cancel)
   if overflow.is_set():raise ArchiveError('一覧・処理ログが4 MiBを超えました。対象を減らしてください。')
   if time.monotonic()>deadline:raise TimeoutError('処理時間の上限（5分）に達しました。')
   if watch and time.monotonic()-last>.2:scan(watch,cancel);last=time.monotonic()
   time.sleep(.04)
  for t in threads:t.join(timeout=2)
  if any(t.is_alive() for t in threads):raise ArchiveError('処理の終了を確認できませんでした。')
  check_cancel(cancel)
  if overflow.is_set():raise ArchiveError('一覧・処理ログが4 MiBを超えました。')
  text=b'\n'.join(bufs).decode('utf8',errors='replace')
  if password:text=text.replace(password,'（パスワード非表示）')
  if proc.returncode:raise ArchiveError('処理できませんでした。書庫・パスワード・形式を確認してください。\n'+text[-3500:])
  if re.search(r'skipping (?:unsafe|7z entry|entry)|refusing unsafe',text,re.I):raise ArchiveError('安全に展開できない項目がありました。結果は保存しません。')
  return text
 finally:
  if proc.poll() is None:proc.kill()
  proc.wait(timeout=10)
  for s in [proc.stdout,proc.stderr]:s.close()
  for t in threads:t.join(timeout=2)

def compress(paths,dest,options,cancel):
 paths=inputs(paths,cancel,True);dest=Path(os.path.abspath(dest));parent=safe_path(dest.parent)
 if options.get('format','').split('.')[0] not in ('zip','tar','7z') and (len(paths)!=1 or not paths[0].is_file()):raise ArchiveError('複数ファイル・フォルダーにはZIP、7z、tar.gzなどの書庫形式を選んでください。')
 if dest.exists() or not parent.is_dir():raise ArchiveError('既存ファイルは上書きできません。新しい保存名を選んでください。')
 entry_name(dest.name)
 if any(p.is_dir() and parent.is_relative_to(p) for p in paths):raise ArchiveError('対象フォルダーの外を保存先に選んでください。')
 stage=Path(tempfile.mkdtemp(prefix='.kiwi-archive-',dir=parent));part=stage/dest.name
 try:
  text=call(build_args('compress',[str(p) for p in paths],str(part),options),cancel,watch=stage)
  if not part.is_file() or part.stat().st_size>LIMIT:raise ArchiveError('圧縮ファイルを確認できませんでした。')
  check_cancel(cancel);part.rename(dest);return text
 finally:cleanup(stage,parent)

def extract(path,parent,options,cancel,password=''):
 path=inputs([path],cancel)[0];parent=safe_path(parent)
 if not parent.is_dir():raise ArchiveError('展開先の親フォルダーを選んでください。')
 preflight(path,cancel);stage=Path(tempfile.mkdtemp(prefix='.kiwi-archive-',dir=parent));out=stage/'contents'
 final=parent/('展開-'+time.strftime('%Y%m%d-%H%M%S')+'-'+stage.name.rsplit('-',1)[-1])
 try:
  text=call(build_args('decompress',[str(path)],str(out),options),cancel,password,stage)
  if not out.is_dir():raise ArchiveError('展開結果がありません。形式を確認してください。')
  verify_tree(out,cancel);check_cancel(cancel);out.rename(final);return final,text
 finally:cleanup(stage,parent)

def listing(paths,options,cancel,password=''):
 paths=inputs(paths,cancel)
 return call(build_args('list',[str(p) for p in paths],options=options),cancel,password)

def save_text(path,text):
 with open(path,'x',encoding='utf8',newline='\n') as f:f.write(text)
