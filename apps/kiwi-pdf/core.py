"""Managed PDF jobs using the bundled qpdf executable."""
import ctypes,hashlib,io,json,os,re,secrets,shutil,sys,tempfile,threading,time,zipfile
from pathlib import Path
if not getattr(sys,'frozen',False):sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'common'))
from runtime import execute,resource_path

MAX_INPUT=200*1024**2;MAX_TOTAL=500*1024**2;MAX_OUTPUT=300*1024**2
_NATIVE_MANAGER=None
def native_folder():
    global _NATIVE_MANAGER
    if not getattr(sys,'frozen',False):return Path(__file__).parent/'native'
    if _NATIVE_MANAGER is not None:return Path(_NATIVE_MANAGER.name)
    pin=json.loads(Path(resource_path('upstream-pin.json')).read_text(encoding='utf8'))
    host=json.loads(Path(resource_path('host-pin.json')).read_text(encoding='utf8'))
    members={**pin['members'],'KiwiPdfHost.exe':host['sha256']}
    manager=tempfile.TemporaryDirectory(prefix='kiwi-pdf-native-')
    try:
        with zipfile.ZipFile(resource_path('native-payload.zip')) as z:
            if set(z.namelist())!={'qpdf.exe','qpdf30.dll','KiwiPdfHost.exe'} or set(members)!=set(z.namelist()):raise ValueError('同梱エンジンの内容が一致しません。')
            for name,digest in members.items():
                body=z.read(name)
                if hashlib.sha256(body).hexdigest()!=digest:raise ValueError('同梱エンジンが一致しません。')
                (Path(manager.name)/name).write_bytes(body)
    except Exception:manager.cleanup();raise
    _NATIVE_MANAGER=manager;return Path(manager.name)

BLOCKED={'inputFile','outputFile','empty','replaceInput','passwordFile','jobJsonFile','global','linearizePass1','jsonStreamPrefix','jsonInput','updateFromJson','staticAesIv','staticId','showEncryptionKey','allowWeakCrypto','allowInsecure','forceR5','testJsonSchema','Bits'}
def validate_extra(extra):
    schema=json.loads(Path(resource_path('job-schema.json',Path(__file__).parent)).read_text(encoding='utf8'))
    def visit(value,shape,depth=0):
        if depth>8:raise ValueError('詳細設定の入れ子が深すぎます。')
        if isinstance(shape,dict):
            if not isinstance(value,dict):raise ValueError('設定はオブジェクトで指定してください。')
            for key,item in value.items():
                if key not in shape or key in BLOCKED:raise ValueError('この設定は使用できません: '+str(key))
                visit(item,shape[key],depth+1)
        elif isinstance(shape,list):
            if not isinstance(value,list) or len(value)>500:raise ValueError('設定の配列が不正です。')
            for item in value:visit(item,shape[0],depth+1)
        elif not isinstance(value,str) or '\x00' in value:raise ValueError('設定値はNULを含まない文字列で指定してください。')
    visit(extra,schema)
    if extra.get('jsonStreamData')=='file':raise ValueError('外部ストリームファイルへの書き出しには対応していません。')
    if 'splitPages' in extra and (not extra['splitPages'].isdigit() or not 1<=int(extra['splitPages'])<=500):raise ValueError('分割は1〜500ページ単位で指定してください。')

def _ready():
    if os.name!='nt':raise ValueError('Windows 11 x64で実行してください。')
    try:
        for name in ('MSVCP140.dll','VCRUNTIME140.dll','VCRUNTIME140_1.dll'):ctypes.WinDLL(name,winmode=0x800)
    except OSError as e:raise ValueError('Microsoft Visual C++ v14 (x64)をインストールしてからお試しください。') from e

def _rows(rows):
    if not isinstance(rows,list) or not 1<=len(rows)<=50:raise ValueError('PDFを1〜50件選んでください。')
    total=0;seen=set();out=[]
    for row in rows:
        p=Path(row['path']).resolve()
        if not p.is_file() or p.suffix.lower()!='.pdf':raise ValueError('PDFが見つかりません: '+p.name)
        if p.stat().st_size>MAX_INPUT:raise ValueError('PDFは1件200 MiBまでです。')
        if str(p).casefold() not in seen:total+=p.stat().st_size;seen.add(str(p).casefold())
        pages=str(row.get('pages',''));password=str(row.get('password',''))
        if '\x00' in pages+password or len(pages)>4096 or len(password.encode('utf8'))>1024:raise ValueError('ページ範囲またはパスワードが長すぎます。')
        out.append(dict(path=str(p),pages=pages,password=password))
    if total>MAX_TOTAL:raise ValueError('入力PDFの合計は500 MiBまでです。')
    return out

def _extra_files(job,base):
    found=set()
    def visit(node):
        if isinstance(node,dict):
            for key,value in node.items():
                if key in ('file','copyEncryption') and isinstance(value,str) and value!='.':
                    p=Path(value);p=(p if p.is_absolute() else base/p).resolve()
                    if not value or not p.is_file() or p.stat().st_size>MAX_INPUT:raise ValueError('参照ファイルを確認してください: '+p.name)
                    node[key]=str(p);found.add(p)
                else:visit(value)
        elif isinstance(node,list):
            for item in node:visit(item)
    visit(job)
    if len(found)>50 or sum(p.stat().st_size for p in found)>MAX_TOTAL:raise ValueError('参照ファイルが多すぎます。')
    return found

def _invoke(job,work,cancel,deadline):
    if cancel.is_set():raise InterruptedError('処理を停止しました。')
    remaining=deadline-time.monotonic()
    if remaining<=0:raise TimeoutError('処理が180秒を超えました。')
    payload=json.dumps(job,ensure_ascii=False).encode('utf8')
    stopped=threading.Event();linked=threading.Event();limit=threading.Event()
    def guard():
        while not stopped.wait(.05):
            if cancel.is_set():linked.set()
            try:
                if sum(p.stat().st_size for p in work.iterdir() if p.is_file())>MAX_OUTPUT:limit.set();linked.set()
            except OSError:pass
    watcher=threading.Thread(target=guard,daemon=True);watcher.start()
    try:
        folder=native_folder();result=execute(str(folder/'KiwiPdfHost.exe'),[],stdin_data=payload,cwd=str(folder),cancel_event=linked,timeout=remaining,max_output=16*1024**2)
        if limit.is_set():raise ValueError('出力が300 MiBを超えました。')
        if cancel.is_set():raise InterruptedError('処理を停止しました。')
        return result
    except InterruptedError:
        if limit.is_set():raise ValueError('出力が300 MiBを超えました。')
        raise
    finally:stopped.set();watcher.join()

def _text(data):
    text=data.decode('utf8',errors='replace')
    return re.sub(r'(?im)^.*(?:user password\s*=|owner password\s*=|encryption key\s*=).*$','[パスワード情報は表示しません]',text)

def run_job(rows,op,destination,options,cancel):
    _ready();rows=_rows(rows);job,kind=build_job(rows,op,options)
    refs=_extra_files(job,Path(rows[0]['path']).parent);sources={str(p).casefold() for p in refs}|{r['path'].casefold() for r in rows}
    target=None if op=='count' else Path(destination).resolve()
    if target is not None:
        if not str(destination).strip() or '\x00' in str(destination):raise ValueError('保存先を指定してください。')
        if str(target).casefold() in sources or target.exists():raise ValueError('保存先にファイルがあるため上書きしません。別の名前を選んでください。')
        suffixes={'pdf':'.pdf','zip':'.zip','report':'.txt','json-report':'.json','json-file':'.json','binary':'.bin','predicate':'.txt'}
        if target.suffix.lower()!=suffixes[kind]:raise ValueError('この処理の保存先は '+suffixes[kind]+' にしてください。')
        target.parent.mkdir(parents=True,exist_ok=True)
    deadline=time.monotonic()+180
    with tempfile.TemporaryDirectory(prefix='kiwi-pdf-job-') as td:
        work=Path(td);output=work/('result.json' if kind=='json-file' else 'result.pdf')
        if kind in ('pdf','zip','json-file'):job['outputFile']=str(output)
        result=_invoke(job,work,cancel,deadline);rc=result['returncode'];log=_text(result['stderr'])
        if kind=='predicate':
            if rc not in (0,2,3):raise ValueError(log or 'PDFを調べられませんでした。')
            data=('qpdf判定コード: '+str(rc)+'\n'+_text(result['stdout'])).encode('utf8')
        else:
            if rc not in (0,3):raise ValueError(log or _text(result['stdout']) or 'PDFを処理できませんでした。')
            if kind=='json-report':data=result['stdout'];json.loads(data)
            elif kind=='report':data=_text(result['stdout']).encode('utf8')
            elif kind=='binary':data=result['stdout']
            elif kind=='json-file':
                if not output.is_file() or output.stat().st_size>MAX_OUTPUT:raise ValueError('JSON出力を確認できません。')
                data=output.read_bytes();json.loads(data)
            else:
                files=sorted(work.glob('result-*.pdf')) if kind=='zip' else [output]
                if not files or len(files)>500 or sum(p.stat().st_size for p in files if p.is_file())>MAX_OUTPUT:raise ValueError('PDF出力が空か大きすぎます。')
                password=job.get('encrypt',{}).get('userPassword',job.get('encryptionFilePassword',rows[0]['password']))
                if 'decrypt' in job:password=''
                for p in files:
                    if not p.is_file():raise ValueError('PDFが出力されませんでした。')
                    check={'inputFile':str(p),'check':''}
                    if password:check['password']=password
                    proof=_invoke(check,work,cancel,deadline)
                    if proof['returncode'] not in (0,3):raise ValueError('出力PDFの検査に失敗しました。'+_text(proof['stderr']))
                if kind=='zip':
                    buffer=io.BytesIO()
                    with zipfile.ZipFile(buffer,'w',zipfile.ZIP_DEFLATED) as z:
                        for p in files:z.write(p,p.name)
                    data=buffer.getvalue()
                else:data=output.read_bytes()
        if len(data)>MAX_OUTPUT:raise ValueError('出力が300 MiBを超えました。')
        if op=='check':data+=('\n'+log).encode('utf8')
        if target is not None:
            with tempfile.TemporaryDirectory(prefix='kiwi-pdf-save-',dir=target.parent) as stage:
                p=Path(stage)/'result';p.write_bytes(data)
                if cancel.is_set():raise InterruptedError('処理を停止しました。')
                os.rename(p,target)
        return dict(output=str(target) if target else '',kind=kind,data=data,log=log,warning=rc==3,size=len(data))

def build_job(rows, op, options):
    if not isinstance(rows, list) or not rows:
        raise ValueError("行が空です")
    if len(rows) > 50:
        raise ValueError("行が多すぎます（最大50）")
    for r in rows:
        p = r.get('path', '')
        pg = r.get('pages', '')
        pw = r.get('password', '')
        if not isinstance(p, str) or '\x00' in p or len(p) > 4096:
            raise ValueError("無効なパスです")
        if not isinstance(pg, str) or '\x00' in pg or len(pg) > 4096:
            raise ValueError("無効なページ範囲です")
        if not isinstance(pw, str):
            raise ValueError("パスワードが無効です")

    opts = options if isinstance(options, dict) else {}
    base = {'inputFile': rows[0]['path']}
    pw0 = rows[0].get('password', '')
    if pw0:
        base['password'] = pw0

    def _pages_entry(row):
        e = {'file': row['path'], 'range': row.get('pages') or '1-z'}
        if row.get('password'):
            e['password'] = row['password']
        return e

    if op == 'merge':
        job = dict(base)
        job['pages'] = [_pages_entry(r) for r in rows]
        return job, 'pdf'

    elif op == 'extract':
        if len(rows) != 1:
            raise ValueError("抽出は1行のみです")
        job = dict(base)
        pg = rows[0].get('pages') or '1-z'
        job['pages'] = [{'file': '.', 'range': pg}]
        return job, 'pdf'

    elif op == 'split':
        if len(rows) != 1:
            raise ValueError("分割は1行のみです")
        sp = opts.get('chunk',opts.get('splitPages'))
        if not isinstance(sp, str) or not sp.isdigit() or not (1 <= int(sp) <= 500):
            raise ValueError("無効な分割数です（1-500）")
        job = dict(base)
        job['splitPages'] = sp
        pg = rows[0].get('pages')
        if pg and pg != '1-z':
            job['pages'] = [{'file': '.', 'range': pg}]
        return job, 'zip'

    elif op == 'rotate':
        if len(rows) != 1:
            raise ValueError("回転は1行のみです")
        ang = opts.get('angle')
        if ang not in ('+90', '-90', '+180', '0'):
            raise ValueError("無効な角度です")
        job = dict(base)
        pg = rows[0].get('pages') or '1-z'
        job['rotate'] = [f"{ang}:{pg}"]
        return job, 'pdf'

    elif op == 'optimize':
        if len(rows) != 1:
            raise ValueError("最適化は1行のみです")
        job = dict(base)
        job['compressStreams'] = 'y'
        job['recompressFlate'] = ''
        job['compressionLevel'] = '9'
        job['objectStreams'] = 'generate'
        if opts.get('lossy'):
            job['optimizeImages'] = ''
            job['jpegQuality'] = '85'
        if opts.get('web'):
            job['linearize'] = ''
        return job, 'pdf'

    elif op == 'protect':
        if len(rows) != 1:raise ValueError("パスワード設定はPDFを1件選んでください。")
        job=dict(base)
        job['encrypt']=make_encryption(opts.get('open_password'),opts.get('owner_password',''))
        return job,'pdf'

    elif op == 'unlock':
        if len(rows) != 1:
            raise ValueError("解除は1行のみです")
        job = dict(base)
        job['decrypt'] = ''
        return job, 'pdf'

    elif op == 'check':
        if len(rows) != 1:
            raise ValueError("チェックは1行のみです")
        job = dict(base)
        job['check'] = ''
        return job, 'report'

    elif op == 'count':
        if len(rows) != 1:
            raise ValueError("カウントは1行のみです")
        job = dict(base)
        job['showNpages'] = ''
        return job, 'report'

    elif op == 'advanced':
        if len(rows) != 1:
            raise ValueError("詳細は1行のみです")
        adv = opts.get('advanced')
        if isinstance(adv, str):
            try:
                adv = json.loads(adv)
            except Exception:
                raise ValueError("詳細オプションのJSONが無効です")
        if not isinstance(adv, dict):
            raise ValueError("詳細オプションはオブジェクトです")
        if len(json.dumps(adv).encode('utf-8')) > 65536:
            raise ValueError("詳細オプションが大きすぎます（最大65536バイト）")
        validate_extra(adv)
        extra = json.loads(json.dumps(adv))

        enc = extra.get('encrypt')
        if isinstance(enc, dict):
            modes = [k for k in ('256bit', '128bit', '40bit') if k in enc]
            if len(modes) != 1:
                raise ValueError("暗号化モードは1つだけです")
            if modes[0] == '40bit':
                raise ValueError("40ビット暗号化は拒否されます")
            if modes[0] == '128bit' and enc.get('128bit',{}).get('useAes') != 'y':
                raise ValueError("128ビットにはuseAes:'y'が必要です")
            for k in ('userPassword', 'ownerPassword'):
                v = enc.get(k, '')
                if not isinstance(v, str) or len(v.encode('utf-8')) > 127:
                    raise ValueError(f"{k}が無効です")
            if 'allowInsecure' in enc.get('256bit', {}):
                raise ValueError("allowInsecureは拒否されます")
            if 'forceR5' in enc.get('256bit', {}):
                raise ValueError("forceR5は拒否されます")

        job = dict(base)
        job.update(extra)

        kind = 'pdf'
        if 'splitPages' in extra: kind = 'zip'
        elif 'jsonOutput' in extra: kind = 'json-file'
        elif 'showAttachment' in extra or 'filteredStreamData' in extra or 'rawStreamData' in extra: kind = 'binary'
        elif 'json' in extra: kind = 'json-report'
        elif 'isEncrypted' in extra or 'requiresPassword' in extra: kind = 'predicate'
        else:
            rep_keys = ['check','checkLinearization','showEncryption','showLinearization','showNpages','showObject','showPages','showXref','listAttachments']
            if any(k in extra for k in rep_keys): kind = 'report'

        return job, kind

    else:
        raise ValueError(f"未知の操作です: {op}")

def make_encryption(user, owner=''):
    if not isinstance(user, str) or '\x00' in user or not (1 <= len(user.encode('utf-8')) <= 127):
        raise ValueError("ユーザーパスワードが無効です（1-127バイト、NUL禁止）")
    if not isinstance(owner, str) or '\x00' in owner:
        raise ValueError("オーナーパスワードが無効です（文字列、NUL禁止）")
    ob = len(owner.encode('utf-8'))
    if ob > 127:
        raise ValueError("オーナーパスワードが長すぎます（最大127バイト）")
    if not owner:
        owner = secrets.token_urlsafe(24)
    return {'userPassword': user, 'ownerPassword': owner, '256bit': {}}
