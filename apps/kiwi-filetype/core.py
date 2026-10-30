"""Read-only content type inspection with bounded native execution."""
import csv,io,json,math,os,re,stat,sys,tempfile
from pathlib import Path
from consumer_runtime import Engine,check,safe_path,save_file
ROOT=Path(sys.executable).parent if getattr(sys,'frozen',False) else Path(__file__).resolve().parent
ENGINE=Engine(ROOT)
MAX_FILES=500
def version(cancel):
 with tempfile.TemporaryDirectory(prefix='kiwi-filetype-version-') as td:
  return ENGINE.call(['--version'],Path(td),cancel,timeout=10,cap=65536).decode('utf8','replace').strip()
def collect(values,recursive,cancel):
 if not values or len(values)>200:raise ValueError('入力を1～200件選んでください。')
 found=[];seen=set();skipped=0;visited=0;total=0
 def visit(value,depth):
  nonlocal skipped,visited,total
  check(cancel);visited+=1
  if visited>6000 or depth>32:raise ValueError('フォルダーの項目数・階層が上限を超えました。範囲を絞ってください。')
  path=Path(value).absolute();key=os.path.normcase(str(path))
  if key in seen:return
  seen.add(key)
  try:
   info=path.lstat()
   if path.is_symlink() or getattr(info,'st_file_attributes',0)&stat.FILE_ATTRIBUTE_REPARSE_POINT:skipped+=1;return
   path=safe_path(path)
   if path.is_dir():
    with os.scandir(path) as entries:
     for entry in entries:
      check(cancel)
      if entry.is_dir(follow_symlinks=False) and not recursive:
       skipped+=1;visited+=1
       if visited>6000:raise ValueError('フォルダーの項目数が上限を超えました。')
       continue
      visit(entry.path,depth+1)
   elif stat.S_ISREG(info.st_mode):
    if info.st_size>2*1024**3:raise ValueError('1ファイル2 GiBまでです。')
    total+=info.st_size;found.append(str(path))
    if len(found)>MAX_FILES or total>20*1024**3:raise ValueError('500ファイル・合計20 GiBまでです。')
   else:skipped+=1
  except PermissionError:skipped+=1
 for value in values:visit(value,0)
 if not found:raise ValueError('調べられる通常ファイルがありません。')
 return sorted(found,key=str.casefold),skipped

def inspect(values,recursive,cancel,stdin=None):
 if stdin is not None:
  if not isinstance(stdin,bytes) or len(stdin)>2*1024**2:raise ValueError('標準入力は2 MiBまでです。')
  paths=['-'];skipped=0
 else:paths,skipped=collect(values,recursive,cancel)
 records=[]
 # Fixed small batches avoid the Windows command line length limit.
 chunks=[];batch=[];length=0
 for path in paths:
  if len(path)>4000:raise ValueError('ファイルのパスが長すぎます。')
  units=len(path.encode('utf-16-le'))//2
  if batch and (length+units>16000 or len(batch)>=50):chunks.append(batch);batch=[];length=0
  batch.append(path);length+=units+4
 if batch:chunks.append(batch)
 for batch in chunks:
  check(cancel)
  with tempfile.TemporaryDirectory(prefix='kiwi-filetype-') as td:
   raw=ENGINE.call(['--json','--no-colors','--no-dereference','--',*batch],Path(td),cancel,timeout=60,stdin=stdin,cap=8*1024**2)
  data=json.loads(raw)
  if not isinstance(data,list) or len(data)!=len(batch):raise ValueError('判定結果の件数が一致しません。')
  for expected,record in zip(batch,data):
   if not isinstance(record,dict) or record.get('path')!=expected:raise ValueError('判定結果の入力が一致しません。')
   result=record.get('result')
   if not isinstance(result,dict) or not isinstance(result.get('status'),str):raise ValueError('判定結果の形式が不正です。')
   if result['status']=='ok':
    value=result.get('value',{});output=value.get('output',{});score=value.get('score')
    if not isinstance(score,(float,int)) or not math.isfinite(score) or not 0<=score<=1:raise ValueError('判定スコアが不正です。')
    for key in ['description','label','group','mime_type']:
     if not isinstance(output.get(key),str) or len(output[key])>1000:raise ValueError('判定結果が不正です。')
    if not isinstance(output.get('extensions'),list) or len(output['extensions'])>100:raise ValueError('拡張子候補が不正です。')
    if any(not isinstance(x,str) or len(x)>50 for x in output['extensions']):raise ValueError('拡張子候補が不正です。')
   records.append(record)
 return {'records':records,'skipped':skipped,'stdin':stdin is not None}

def row(record):
 result=record['result'];value=result.get('value',{});output=value.get('output',{})
 return [record['path'],output.get('description',result['status']),', '.join(output.get('extensions',[])),output.get('mime_type',''),output.get('label',''),output.get('group',''),f"{value['score']:.3f}" if 'score' in value else '']

def custom(record,pattern):
 if not isinstance(pattern,str) or len(pattern)>500:raise ValueError('表示書式は500文字までです。')
 value=record['result'].get('value',{});output=value.get('output',{});dl=value.get('dl',{});score=value.get('score')
 mapping={'p':record['path'],'l':output.get('label',''),'d':output.get('description',record['result']['status']),'g':output.get('group',''),'m':output.get('mime_type',''),'e':','.join(output.get('extensions',[])),'s':str(score) if score is not None else '', 'S':f'{score*100:.2f}' if score is not None else '', 'b':dl.get('label','') if dl.get('label')!=output.get('label') else '', '%':'%'}
 if '%' in re.sub(r'%[pldgmesSb%]','',pattern):raise ValueError('書式は %p %l %d %g %m %e %s %S %b %% を使えます。')
 return re.sub(r'%([pldgmesSb%])',lambda match:mapping[match[1]],pattern)

def report(result,kind,pattern='%p: %d'):
 data=result['records']
 if kind=='JSON':return json.dumps(data,ensure_ascii=False,indent=2)+'\n'
 if kind=='JSONL':return ''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in data)
 if kind=='CSV':
  stream=io.StringIO();writer=csv.writer(stream);writer.writerow(['ファイル','種類','候補拡張子','MIME','ラベル','分類','推定スコア'])
  for record in data:
   cells=row(record)
   # Neutralize spreadsheet formula prefixes in untrusted filenames.
   writer.writerow(["'"+x if x.startswith(('=','+','-','@','\t','\r')) else x for x in cells])
  return stream.getvalue()
 if kind=='MIME':pattern='%p: %m'
 elif kind=='ラベル':pattern='%p: %l'
 elif kind=='説明':pattern='%p: %d'
 elif kind!='書式指定':raise ValueError('出力形式を選んでください。')
 return '\n'.join(custom(r,pattern) for r in data)+'\n'

def save(result,kind,pattern,folder,cancel):
 body=report(result,kind,pattern).encode('utf-8-sig' if kind=='CSV' else 'utf8')
 if len(body)>16*1024**2:raise ValueError('保存結果は16 MiBまでです。')
 with tempfile.TemporaryDirectory(prefix='kiwi-filetype-report-') as td:
  source=Path(td)/'report';source.write_bytes(body)
  return save_file(source,folder,'file-types',{'JSON':'.json','JSONL':'.jsonl','CSV':'.csv'}.get(kind,'.txt'),cancel)
