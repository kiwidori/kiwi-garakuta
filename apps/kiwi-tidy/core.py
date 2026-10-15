"""Read-only scans using the bundled Czkawka CLI."""
import csv,hashlib,io,json,os,re,subprocess,tempfile,threading,time,zipfile
from pathlib import Path
from runtime import resource_path
from options import option_flags,result_groups
ROOT=Path(__file__).resolve().parent
_NATIVE=None
_LOCK=threading.Lock()
MODES={'dup':'同じファイル','image':'似た写真','empty-folders':'空のフォルダー','empty-files':'空のファイル','big':'大きい・小さいファイル','temp':'一時ファイル','music':'同じ音楽','symlinks':'リンク切れ','broken':'壊れたファイル','ext':'拡張子の不一致','bad-names':'気になるファイル名','exif-remover':'写真の撮影情報'}

def native_exe():
 global _NATIVE
 with _LOCK:
  if _NATIVE is None:
   pin=json.loads(Path(resource_path('upstream-pin.json',ROOT)).read_text(encoding='utf8'))
   with zipfile.ZipFile(resource_path('native-payload.zip',ROOT)) as z:b=z.read('czkawka.exe')
   if hashlib.sha256(b).hexdigest()!=pin['sha256']:raise ValueError('同梱プログラムの検証に失敗しました。')
   _NATIVE=tempfile.TemporaryDirectory(prefix='kiwi-tidy-native-');(Path(_NATIVE.name)/'czkawka.exe').write_bytes(b)
  return Path(_NATIVE.name)/'czkawka.exe'

def folders(items,required=False):
 if not isinstance(items,list) or len(items)>32:raise ValueError('各種類のフォルダーは32件までです。')
 out=[]
 for text in items:
  p=Path(text)
  if not isinstance(text,str) or not p.is_absolute() or any(ord(c)<32 for c in text):raise ValueError('フォルダーを絶対パスで指定してください。')
  p=p.resolve(strict=True)
  if not p.is_dir():raise ValueError('フォルダーではありません: '+str(p))
  if str(p).casefold() not in [s.casefold() for s in out]:out.append(str(p))
 if required and not out:raise ValueError('対象フォルダーを選んでください。')
 return out

def scan(mode,directories,excluded,references,options,cancel):
 if mode not in MODES:raise ValueError('使えない操作です。')
 ds=folders(directories,True);es=folders(excluded);rs=folders(references)
 if rs and mode not in ('dup','image','music'):raise ValueError('基準フォルダーは重複・似た写真・音楽の検索で使えます。')
 # Native reference folders must be part of the searched directory set.
 args=[mode,'-W','-N','-H']
 for name,items in [('directories',ds+[r for r in rs if r not in ds]),('excluded-directories',es),('reference-directories',rs)]:
  args.extend('--'+name+'='+value for value in items)
 args+=option_flags(mode,options)
 if cancel.is_set():raise InterruptedError('検索を停止しました。')
 with tempfile.TemporaryDirectory(prefix='kiwi-tidy-job-') as tmp:
  job=Path(tmp);report=job/'result.json';text=job/'result.txt';log=job/'log.txt'
  env=os.environ.copy()
  for key in list(env):
   if key.upper().startswith('CZKAWKA_'):del env[key]
  for name in ('config','cache'):(job/name).mkdir()
  env['CZKAWKA_CONFIG_PATH']=str(job/'config');env['CZKAWKA_CACHE_PATH']=str(job/'cache');env['RUST_LOG']='warn'
  with log.open('wb') as f:
   proc=subprocess.Popen([str(native_exe()),*args,'-p',str(report),'-f',str(text)],stdin=subprocess.DEVNULL,stdout=f,stderr=subprocess.STDOUT,cwd=job,env=env,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
   start=time.monotonic()
   try:
    while proc.poll() is None:
     if cancel.is_set():raise InterruptedError('検索を停止しました。')
     if time.monotonic()-start>1800:raise TimeoutError('30分以内に完了しなかったため停止しました。対象を小さくしてください。')
     if log.stat().st_size>4*1024*1024 or any(p.exists() and p.stat().st_size>16*1024*1024 for p in (report,text)):raise ValueError('結果が上限を超えました。対象を小さくしてください。')
     time.sleep(.05)
   finally:
    if proc.poll() is None:proc.kill()
    proc.wait()
  if cancel.is_set():raise InterruptedError('検索を停止しました。')
  notes=log.read_text(encoding='utf8',errors='replace')[-20000:]
  if proc.returncode!=0 or not report.is_file() or not text.is_file():raise ValueError('検索を完了できませんでした。\n'+notes[-3000:])
  if report.stat().st_size>16*1024*1024 or text.stat().st_size>16*1024*1024:raise ValueError('結果が16 MiBを超えました。')
  raw=report.read_bytes();data=json.loads(raw.decode('utf8'));groups=result_groups(mode,options.get('search-method','HASH'),data)
  return {'mode':mode,'groups':groups,'raw':raw,'text':text.read_bytes(),'notes':notes,'options':options}

def export_report(result,path,kind):
 path=Path(path)
 if kind=='json':b=result['raw']
 elif kind=='txt':b=result['text']
 elif kind=='csv':
  s=io.StringIO(newline='');w=csv.writer(s);w.writerow(['グループ','基準','パス','サイズ','幅','高さ','差'])
  for i,group in enumerate(result['groups'],1):
   for row in group:
    values=[i,'基準' if row.get('reference') else '',row['path'],row.get('size',''),row.get('width',''),row.get('height',''),row.get('difference','')]
    w.writerow(["'"+v if isinstance(v,str) and v.lstrip().startswith(('=','+','-','@')) else v for v in values])
  b=s.getvalue().encode('utf-8-sig')
 else:raise ValueError('TXT、JSON、CSVを選んでください。')
 with path.open('xb') as f:f.write(b)
 return path
