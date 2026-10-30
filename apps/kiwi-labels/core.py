"""Render fixed label layouts without evaluating user-provided markup."""
import ctypes,os,re,subprocess,sys,tempfile,time
from pathlib import Path
from consumer_runtime import Engine,NativeJob,check,safe_path,save_file
from layout import source
ROOT=Path(sys.executable).parent if getattr(sys,'frozen',False) else Path(__file__).resolve().parent
ENGINE=Engine(ROOT)

def windows_fonts():
 buf=ctypes.create_unicode_buffer(32768)
 n=ctypes.windll.kernel32.GetWindowsDirectoryW(buf,len(buf))
 if not 0<n<len(buf):raise OSError('Windowsのフォントを確認できません。')
 return Path(buf.value)/'Fonts'

def call(args,work,cancel):
 check(cancel);env={k:v for k,v in os.environ.items() if not k.startswith('TYPST_') and k!='SOURCE_DATE_EPOCH'}
 with (work/'stdout.log').open('wb') as out,(work/'stderr.log').open('wb') as err:
  group=NativeJob();proc=None
  try:
   proc=subprocess.Popen([str(ENGINE.executable()),*args],cwd=work,env=env,stdin=subprocess.DEVNULL,stdout=out,stderr=err,creationflags=subprocess.CREATE_NO_WINDOW);group.attach(proc)
   deadline=time.monotonic()+30
   while proc.poll() is None:
    check(cancel)
    sizes=[p.stat().st_size for p in work.rglob('*') if p.is_file()]
    if time.monotonic()>deadline:raise ValueError('作成時間の上限（30秒）に達しました。')
    if any(x>20*1024**2 for x in sizes) or sum(sizes)>64*1024**2:raise ValueError('作成サイズの上限を超えました。')
    time.sleep(.05)
  finally:
   group.close()
   if proc is not None:proc.wait(timeout=10)
 check(cancel)
 sizes=[p.stat().st_size for p in work.rglob('*') if p.is_file()]
 if any(x>20*1024**2 for x in sizes) or sum(sizes)>64*1024**2:raise ValueError('作成サイズの上限を超えました。')
 error=(work/'stderr.log').read_bytes()[-2500:].decode('utf8','replace')
 if proc.returncode or 'warning:' in error:raise ValueError('文字・フォント・設定を確認してください。\n'+error.replace(str(work),'作業フォルダー'))
 return (work/'stdout.log').read_bytes()

def fonts(cancel):
 with tempfile.TemporaryDirectory(prefix='kiwi-label-fonts-') as td:
  raw=call(['fonts','--ignore-system-fonts','--ignore-embedded-fonts','--font-path',str(windows_fonts())],Path(td),cancel)
  values=raw.decode('utf8').splitlines()
  if not 0<len(values)<=5000 or any(not x.strip() or len(x)>120 or any(ord(c)<32 for c in x) for x in values):raise ValueError('フォント一覧を確認できません。')
  return sorted(set(values),key=str.casefold)

def parse_pages(value,total):
 if not isinstance(value,str) or len(value)>128:raise ValueError('保存ページを確認してください。')
 if not value.strip():return list(range(1,total+1))
 chosen=set()
 for part in value.replace(' ','').split(','):
  if not re.fullmatch(r'[0-9]+(?:-[0-9]*)?',part):raise ValueError('保存ページは 1,3-5 のように指定してください。')
  fields=part.split('-');start=int(fields[0]);end=int(fields[1]) if len(fields)==2 and fields[1] else (total if len(fields)==2 else start)
  if not 1<=start<=end<=total:raise ValueError(f'保存ページは1～{total}の範囲で指定してください。')
  chosen.update(range(start,end+1))
 return sorted(chosen)

def render(items,options,cancel,folder=None,preview_page=None,fmt='pdf',ppi=144,page_range='',pdf_standard='1.7',tagged=True):
 if fmt not in {'pdf','png','svg'} or type(ppi) is not int or not 72<=ppi<=200:raise ValueError('保存形式・解像度を確認してください。')
 if pdf_standard not in {'1.4','1.7','2.0','a-2b'} or type(tagged) is not bool:raise ValueError('PDFの形式・タグ設定を確認してください。')
 text,pages=source(items,**options)
 selected=parse_pages(page_range,pages)
 if preview_page is not None and (type(preview_page) is not int or not 1<=preview_page<=pages):raise ValueError(f'プレビューのページは1～{pages}です。')
 if preview_page is not None:fmt='png';ppi=100
 else:safe_path(folder,True)
 with tempfile.TemporaryDirectory(prefix='kiwi-label-job-') as td:
  work=Path(td);(work/'main.typ').write_text(text,encoding='utf8')
  output='preview.png' if preview_page is not None else ('output.pdf' if fmt=='pdf' else 'page-{0p}.'+fmt)
  args=['compile','--root',str(work),'--package-path',str(work/'packages'),'--package-cache-path',str(work/'cache'),'--ignore-system-fonts','--ignore-embedded-fonts','--font-path',str(windows_fonts()),'--jobs','2','--creation-timestamp',str(int(time.time())),'--ppi',str(ppi)]
  if preview_page is not None:args+=['--pages',str(preview_page)]
  else:
   partial=selected!=list(range(1,pages+1))
   if partial:args+=['--pages',','.join(map(str,selected))]
   if fmt=='pdf':
    args+=['--pdf-standard',pdf_standard]
    if not tagged or partial:args+=['--no-pdf-tags']
  call([*args,str(work/'main.typ'),str(work/output)],work,cancel)
  paths=[work/'preview.png'] if preview_page is not None else sorted(work.glob('output.pdf' if fmt=='pdf' else 'page-*.'+fmt))
  if not paths or len(paths)!=(1 if fmt=='pdf' or preview_page is not None else len(selected)) or any(not 0<p.stat().st_size<=20*1024**2 for p in paths) or sum(p.stat().st_size for p in paths)>64*1024**2:raise ValueError('出力の枚数・サイズを確認できません。')
  if preview_page is not None:return {'png':paths[0].read_bytes(),'pages':pages}
  saved=[]
  for i,p in enumerate(paths):
   check(cancel);saved.append(str(save_file(p,folder,'ラベル'+(f'_{i+1:02}' if len(paths)>1 else ''),'.'+fmt,cancel)))
  total_labels=len(items)*options.get('repeat',1);per=options.get('columns',2)*options.get('rows',6)
  count=sum(min(per,max(0,total_labels-(p-1)*per)) for p in selected)
  return {'paths':saved,'pages':len(selected),'total_pages':pages,'labels':count,'tagged':fmt=='pdf' and tagged and not partial}
