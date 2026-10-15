"""Local encrypted, versioned backups through the pinned restic binary."""
import hashlib,json,re,secrets,tempfile,threading,time,zipfile
from pathlib import Path,PurePosixPath,PureWindowsPath
from runtime import resource_path
from native_run import run_native,parse_json,local_repository
ROOT=Path(__file__).resolve().parent
_NATIVE=None
_LOCK=threading.Lock()
COMMON={'compression':'str'}
SCHEMA={
'backup':{'exclude':'list','iexclude':'list','exclude-caches':'bool','exclude-if-present':'list','exclude-larger-than':'str','force':'bool','ignore-ctime':'bool','ignore-inode':'bool','no-scan':'bool','one-file-system':'bool','parent':'str','read-concurrency':'int','skip-if-unchanged':'bool','time':'str','with-atime':'bool'},
'snapshots':{'host':'list','tag':'list','path':'list','latest':'int'},'ls':{'sort':'str','reverse':'bool'},
'restore':{'exclude':'list','iexclude':'list','include':'list','iinclude':'list','sparse':'bool'},
'find':{'ignore-case':'bool','newest':'str','oldest':'str','reverse':'bool','host':'list','tag':'list','path':'list'},
'diff':{'metadata':'bool'},'stats':{'mode':'str'},'check':{'read-data':'bool','read-data-subset':'str'},
'forget':{**{k:'int' for k in ('keep-last','keep-hourly','keep-daily','keep-weekly','keep-monthly','keep-yearly')},**{k:'str' for k in ('keep-within','keep-within-hourly','keep-within-daily','keep-within-weekly','keep-within-monthly','keep-within-yearly')},'keep-tag':'list','host':'list','tag':'list','path':'list'},
'prune':{'dry-run':'bool','max-unused':'str','max-repack-size':'str','repack-cacheable-only':'bool','repack-uncompressed':'bool','repack-smaller-than':'str'},
'init':{},'tag':{},'copy':{},'unlock':{},'dump':{},'key':{}}
ENUMS={'compression':('auto','off','fastest','better','max'),'sort':('name','size','time','mtime','atime','ctime','extension'),'mode':('restore-size','files-by-contents','raw-data','blobs-per-file')}

def native_exe():
 global _NATIVE
 with _LOCK:
  if _NATIVE is None:
   pin=json.loads(Path(resource_path('upstream-pin.json',ROOT)).read_text(encoding='utf8'))
   with zipfile.ZipFile(resource_path('native-payload.zip',ROOT)) as z:b=z.read('restic.exe')
   if hashlib.sha256(b).hexdigest()!=pin['native_sha256']:raise ValueError('同梱プログラムの検証に失敗しました。')
   _NATIVE=tempfile.TemporaryDirectory(prefix='kiwi-backup-native-');(Path(_NATIVE.name)/'restic.exe').write_bytes(b)
  return Path(_NATIVE.name)/'restic.exe'

def text(value,limit=2048):
 if not isinstance(value,str) or len(value)>limit or any(ord(c)<32 for c in value):raise ValueError('設定値が長すぎるか制御文字を含んでいます。')
 return value

def flags(op,opts):
 if not isinstance(opts,dict) or op not in SCHEMA or len(opts)>64:raise ValueError('詳細設定はJSONオブジェクトで指定してください。')
 spec={**SCHEMA[op],**COMMON};out=[]
 for k,v in opts.items():
  if k not in spec:raise ValueError('使えない設定: '+str(k))
  typ=spec[k]
  if typ=='bool':
   if type(v)!=bool:raise ValueError(k+'はtrue/falseで指定します。')
   out.append('--'+k+'='+str(v).lower())
  elif typ=='int':
   if type(v)!=int or not 1<=v<=10000 or (k=='read-concurrency' and v>64):raise ValueError(k+'の数値が範囲外です。')
   out.append('--'+k+'='+str(v))
  elif typ=='list':
   if not isinstance(v,list) or len(v)>64:raise ValueError(k+'は文字列の配列で指定します。')
   for x in v:out.append('--'+k+'='+text(x))
  else:
   x=text(v)
   if k in ENUMS and x not in ENUMS[k]:raise ValueError(k+'の値を確認してください。')
   out.append('--'+k+'='+x)
 return out

def snapshot_id(value):
 if not isinstance(value,str) or not re.fullmatch('[0-9a-f]{64}',value):raise ValueError('保存履歴を選択してください。')
 return value

def scope_path(value):
 text(value,32767)
 if value and (not value.startswith('/') or '..' in PurePosixPath(value).parts):raise ValueError('履歴の一覧に表示された絶対パスを選択してください。')
 return value

def call(repo,password,args,cancel,**kw):return run_native(native_exe(),str(repo),password,args,cancel,**kw)
def records(result):return parse_json(result['stdout'])
def snapshots(repo,password,cancel,opts=None):
 r=records(call(repo,password,['snapshots',*flags('snapshots',opts or {})],cancel));r=r or []
 if not isinstance(r,list) or len(r)>10000:raise ValueError('履歴は10,000件までです。')
 for s in r:snapshot_id(s['id'])
 return sorted(r,key=lambda s:s['time'],reverse=True)

def initialize(repo,password,cancel):
 p=local_repository(str(repo),must_exist=False)
 if len(password)<8 or not password.strip():raise ValueError('新しいパスワードは8文字以上にしてください。')
 if p.exists() and any(p.iterdir()):raise ValueError('新しい保管庫には空のフォルダーを指定してください。')
 return call(p,password,['init'],cancel)

def backup(repo,password,sources,exclude,tags,host,opts,cancel):
 rp=local_repository(str(repo));paths=[]
 if not isinstance(sources,list) or not 1<=len(sources)<=32:raise ValueError('対象ファイル・フォルダーを1～32件選んでください。')
 for item in sources:
  p=Path(item)
  if not p.is_absolute():raise ValueError('対象は絶対パスで指定してください。')
  p=p.resolve(strict=True)
  if p==rp or rp.is_relative_to(p) or p.is_relative_to(rp):raise ValueError('保管庫と保存対象が重なっています。別の保存先を選んでください。')
  if not (p.is_file() or p.is_dir()):raise ValueError('通常のファイル・フォルダーを選んでください。')
  paths.append(str(p))
 args=['backup',*flags('backup',opts)]
 for pattern in exclude:args.append('--exclude='+text(pattern))
 if tags:args.append('--tag='+text(tags))
 if host:args.append('--host='+text(host,255))
 return call(rp,password,[*args,'--',*paths],cancel)

def operate(repo,password,op,ids,opts,cancel,pattern='',tags='',tag_action='add'):
 args=[op,*flags(op,opts)]
 if op in ('ls','diff','stats','tag','dump','find'):
  for i in ids:snapshot_id(i)
 if op=='ls':
  if len(ids)!=1:raise ValueError('履歴を1件選択してください。')
  args+=['--recursive',ids[0]]
 elif op=='diff':
  if len(ids)!=2:raise ValueError('比べる履歴を2件選択してください。')
  args+=list(ids)
 elif op=='stats':args+=list(ids)
 elif op=='find':
  if not text(pattern):raise ValueError('探すファイル名を入力してください。')
  args+=[*['--snapshot='+s for s in ids],'--',pattern]
 elif op=='tag':
  if not ids or len(ids)>32 or tag_action not in ('add','remove','set') or not text(tags):raise ValueError('履歴とタグを指定してください。')
  args+=['--'+tag_action+'='+tags,*ids]
 elif op=='key':args+=['list']
 elif op not in ('check','prune','unlock','snapshots'):raise ValueError('使えない操作です。')
 return call(repo,password,args,cancel)

def restore(repo,password,sid,parent,cancel,scope='',single_file=False,opts=None):
 sid=snapshot_id(sid);scope=scope_path(scope);parent=local_repository(str(parent));rp=local_repository(str(repo))
 if parent==rp or parent.is_relative_to(rp):raise ValueError('保管庫の外に復元してください。')
 stamp=time.strftime('%Y%m%d-%H%M%S')+'-'+secrets.token_hex(3);stage=parent/('復元中-'+stamp);stage.mkdir();result={}
 try:
  if single_file:
   if not scope or scope=='/':raise ValueError('取り出すファイルを選んでください。')
   name=PurePosixPath(scope).name
   if name in ('.','..') or any(c in name for c in '<>:"/\\|?*'):raise ValueError('このファイル名はWindowsでは保存できません。')
   result=call(rp,password,['dump',sid,scope],cancel,max_output=64*1024*1024)
   with (stage/name).open('xb') as f:f.write(result['stdout'])
  elif scope:
   result=call(rp,password,['restore',sid+(':'+scope if scope else ''),'--target',str(stage),'--verify','--overwrite=never',*flags('restore',opts or {})],cancel)
  else:
   # Restore each saved source root directly, avoiding synthetic drive/user
   # ancestors whose Windows ACLs can make a fresh destination inaccessible.
   inventory=snapshots(rp,password,cancel);entry=next((s for s in inventory if s['id']==sid),None)
   if entry is None:raise ValueError('選択した保存履歴がありません。')
   listing=records(operate(rp,password,'ls',[sid],{},cancel));nodes={n['path']:n for n in listing if n.get('message_type')=='node'}
   paths=entry.get('paths',[])
   if not 1<=len(paths)<=32:raise ValueError('保存元は1～32件までです。中身から選んで復元してください。')
   for index,source in enumerate(paths,1):
    wp=PureWindowsPath(source)
    if not wp.is_absolute() or not re.fullmatch('[A-Za-z]:',wp.drive):raise ValueError('この履歴は中身からフォルダーを選んで復元してください。')
    native='/'+wp.drive[0].upper()+'/'+ '/'.join(wp.parts[1:]);native=native.rstrip('/')
    node=nodes.get(native)
    if not node:raise ValueError('保存元を履歴内で確認できません。中身から選んで復元してください。')
    target=stage/(str(index).zfill(2)+'-保存元');target.mkdir()
    if node.get('type')=='dir':
     result=call(rp,password,['restore',sid+':'+native,'--target',str(target),'--verify','--overwrite=never',*flags('restore',opts or {})],cancel)
    elif node.get('type')=='file':
     parent_path=str(PurePosixPath(native).parent);name=PurePosixPath(native).name
     # A scoped restore does not apply the metadata of the scope root.
     # Literal glob escaping keeps brackets in Windows filenames literal.
     pattern=name.replace('[','[[]')
     result=call(rp,password,['restore',sid+':'+parent_path,'--target',str(target),'--include=/'+pattern,'--verify','--overwrite=never'],cancel)
    else:raise ValueError('通常のファイル・フォルダーだけを復元できます。')
  if cancel.is_set():raise InterruptedError('停止しました。')
  final=parent/('復元-'+stamp);stage.rename(final);return {'folder':str(final),'result':result}
 except Exception as e:raise RuntimeError(str(e)+'\n途中の復元先: '+str(stage)) from e

def copy_snapshots(repo,password,destination,dest_password,ids,cancel):
 src=local_repository(str(repo));dst=local_repository(str(destination))
 if src==dst or src.is_relative_to(dst) or dst.is_relative_to(src):raise ValueError('異なる保管庫を選択してください。')
 if not ids or len(ids)>32:raise ValueError('複製する履歴を1～32件選んでください。')
 return call(dst,dest_password,['copy','--from-repo='+str(src),*[snapshot_id(s) for s in ids]],cancel,from_password=password)

def plan_retention(repo,password,opts,cancel):
 from retention import make_plan
 if not any(k.startswith('keep-') for k in opts):raise ValueError('残す履歴の条件を指定してください。')
 inventory=snapshots(repo,password,cancel)
 groups=records(call(repo,password,['forget','--dry-run','--group-by=host,paths',*flags('forget',opts)],cancel))
 plan=make_plan(repo,inventory,groups)
 if len(plan['remove'])>255:raise ValueError('削除予定は1回255件までです。保持条件で削除対象を減らしてください。')
 return plan

def apply_retention(repo,password,plan,cancel):
 from retention import validate_plan
 ids=validate_plan(plan,repo,snapshots(repo,password,cancel))
 return call(repo,password,['forget',*ids],cancel)
