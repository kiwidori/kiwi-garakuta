"""Run fixed, verified native tools and publish only completed local files."""
import hashlib,json,os,re,secrets,subprocess,sys,tempfile,threading,time
from datetime import datetime
from pathlib import Path
ROOT=Path(__file__).resolve().parent
class OutputUnavailable(FileExistsError):pass
ERRORS={'output_unavailable':'保存先が使用中か、同じ名前のファイルがあります。別名を選んでください。','operation_failed':'処理できませんでした。パスワード・鍵・ファイルを確認してください。','invalid_request':'入力を確認してください。'}

def native(name):
 base=Path(getattr(sys,'_MEIPASS',ROOT));pin=json.loads((base/'upstream-pin.json').read_text(encoding='utf8'));p=base/'native'/name
 if not p.is_file() or hashlib.sha256(p.read_bytes()).hexdigest()!=pin['binaries'][name]:raise ValueError('同梱ファイルの検証に失敗しました。配布ZIPを展開し直してください。')
 return p

def call(name,args,payload,cancel,timeout=300):
 if cancel.is_set():raise InterruptedError('停止しました。')
 if len(payload)>2*1024*1024:raise ValueError('入力が大きすぎます。')
 process=subprocess.Popen([str(native(name)),*args],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,creationflags=subprocess.CREATE_NO_WINDOW)
 overflow=threading.Event();buffers=[bytearray(),bytearray()];threads=[]
 def drain(stream,index,limit):
  try:
   while True:
    raw=stream.read(8192)
    if not raw:break
    if len(buffers[index])+len(raw)>limit:overflow.set();break
    buffers[index].extend(raw)
  except (OSError,ValueError):pass
 def feed():
  try:process.stdin.write(payload);process.stdin.close()
  except (OSError,ValueError):pass
 for stream,index,limit in [(process.stdout,0,1024*1024),(process.stderr,1,16384)]:
  t=threading.Thread(target=drain,args=(stream,index,limit),daemon=True);t.start();threads.append(t)
 t=threading.Thread(target=feed,daemon=True);t.start();threads.append(t);deadline=time.monotonic()+timeout
 try:
  while process.poll() is None:
   if cancel.is_set():raise InterruptedError('停止しました。')
   if overflow.is_set():raise ValueError('処理結果が大きすぎます。')
   if time.monotonic()>deadline:raise TimeoutError('処理時間の上限に達しました。')
   time.sleep(.03)
  for t in threads:t.join(timeout=2)
  if any(t.is_alive() for t in threads):raise RuntimeError('処理の終了を確認できませんでした。')
  if overflow.is_set():raise ValueError('処理結果が大きすぎます。')
  if cancel.is_set():raise InterruptedError('停止しました。')
  if process.returncode!=0:raise ValueError('元ツールが処理を完了できませんでした。入力を確認してください。')
  return bytes(buffers[0])
 finally:
  if process.poll() is None:process.kill()
  process.wait(timeout=10)
  for stream in (process.stdin,process.stdout,process.stderr):
   try:stream.close()
   except OSError:pass
  for t in threads:t.join(timeout=2)

def bridge(request,cancel,timeout=300):
 packet=json.loads(call('KiwiVaultBridge.exe',[],json.dumps(request,ensure_ascii=True).encode(),cancel,timeout))
 if isinstance(packet,dict) and packet.get('error')=='output_unavailable':raise OutputUnavailable(ERRORS['output_unavailable'])
 if not isinstance(packet,dict) or packet.get('ok') is not True:raise ValueError(ERRORS.get(packet.get('error') if isinstance(packet,dict) else '',ERRORS['operation_failed']))
 return packet

def inspect(path,cancel):
 p=Path(path)
 if not p.is_file() or p.stat().st_size>768*1024*1024:raise ValueError('暗号化ファイルは768 MiBまでです。')
 return json.loads(call('age-inspect.exe',['--json',str(p.resolve())],b'',cancel,15))

def password(value,encrypt=False):
 if not isinstance(value,str) or not 1<=len(value.encode('utf8'))<=1024 or (encrypt and len(value)<12):raise ValueError('暗号化用のパスワードは12文字以上・UTF-8で1,024バイト以内にしてください。')
 return value

def new_folder(base,op):
 p=Path(base).resolve()
 if not p.is_dir():raise ValueError('保存先の親フォルダーを選んでください。')
 folder=p/('きうい'+('暗号化' if op=='encrypt' else '復号')+'-'+datetime.now().strftime('%Y%m%d-%H%M%S')+'-'+secrets.token_hex(3));folder.mkdir(mode=0o700);return folder

def save(request,final,cancel,timeout=300):
 final=Path(final).resolve()
 if final.exists():raise FileExistsError('同じ名前のファイルがあります。別名で保存してください。')
 stage=Path(tempfile.mkdtemp(prefix='.kiwi-',dir=final.parent));part=stage/'pending';remove=True
 try:
  result=bridge({**request,'output':str(part)},cancel,timeout)
  if cancel.is_set():raise InterruptedError('停止しました。')
  if not part.is_file() or part.stat().st_size!=result.get('size'):raise ValueError('完成ファイルを確認できませんでした。')
  # Windows rename refuses an existing destination, including a racing creator.
  part.rename(final);return result
 except OutputUnavailable:
  remove=False;raise
 finally:
  if remove and part.is_file():part.unlink()
  try:stage.rmdir()
  except OSError:pass

def output_name(index,path,op,armor):
 name=Path(path).name
 if op=='encrypt':name+='.asc' if armor else '.age'
 elif name.lower().endswith(('.age','.asc')):name=name[:-4]
 else:name+='-復号'
 name=re.sub(r'[<>:"/\\|?*\x00-\x1f]','_',name).strip(' .')[:170] or 'file'
 reserved={'CON','PRN','AUX','NUL','CONIN$','CONOUT$',*[f'COM{i}' for i in range(1,10)],*[f'LPT{i}' for i in range(1,10)]}
 if name.split('.')[0].upper() in reserved:name='file_'+name
 return name

def batch(paths,folder,options,cancel,progress):
 op=options['op'];limit=(512 if op=='encrypt' else 768)*1024*1024;items=[];errors=[];total=0
 if not 1<=len(paths)<=32:raise ValueError('ファイルは1～32件までです。')
 for path in paths:
  p=Path(path)
  if not p.is_absolute() or not p.is_file() or p.stat().st_size>limit:raise ValueError('対象ファイルの形式・サイズを確認してください。')
  total+=p.stat().st_size
 if total>2*1024**3:raise ValueError('一度に処理するファイルは合計2 GiBまでです。')
 deadline=time.monotonic()+600;stopped=False;used=set()
 for i,path in enumerate(paths,1):
  if cancel.is_set() or time.monotonic()>deadline:stopped=True;break
  name=output_name(i,path,op,options.get('armor',False));candidate=name;n=0
  while candidate.casefold() in used:
   n+=1;candidate=f'{i:03d}-{n}_'+name
  used.add(candidate.casefold());final=Path(folder)/candidate
  try:
   packet=save({**options,'input':str(Path(path).resolve())},final,cancel,timeout=min(300,max(.1,deadline-time.monotonic())))
   item={'index':i,'input':Path(path).name,'output':final.name,'size':packet['size'],'sha256':packet.get('sha256','')};items.append(item);progress(item,None)
  except InterruptedError:stopped=True;break
  except Exception as e:errors.append(Path(path).name+'：'+str(e));progress(None,{'index':i,'message':errors[-1]})
 return {'items':items,'errors':errors,'stopped':stopped,'folder':str(folder)}
