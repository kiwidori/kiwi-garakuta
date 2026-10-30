"""Pinned croc transport, with isolated settings and dedicated receive folders."""
import hashlib,ipaddress,json,re,secrets,tempfile,threading,time,zipfile
from pathlib import Path
from resource_paths import resource_path
from native_runner import run_native
ROOT=Path(__file__).resolve().parent
_NATIVE=None
_LOCK=threading.Lock()
def native_exe():
    global _NATIVE
    with _LOCK:
        if _NATIVE is None:
            pin=json.loads(Path(resource_path('upstream-pin.json',ROOT)).read_text(encoding='utf8'))
            payload=Path(resource_path('native-payload.zip',ROOT))
            if not payload.is_file():raise ValueError('配布ZIPを展開して起動してください。')
            body=zipfile.ZipFile(payload).read('croc.exe')
            if hashlib.sha256(body).hexdigest()!=pin['native_sha256']:raise ValueError('同梱プログラムの検証に失敗しました。')
            _NATIVE=tempfile.TemporaryDirectory(prefix='kiwi-transfer-native-')
            (Path(_NATIVE.name)/'croc.exe').write_bytes(body)
        return Path(_NATIVE.name)/'croc.exe'
def valid_code(code):
    code=code.strip()
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9-]{5,127}',code):raise ValueError('共有コードは6～128文字の半角英数字とハイフンで入力してください。URLは使えません。')
    return code
def new_code():return secrets.token_hex(4)+'-'+secrets.token_hex(4)+'-'+secrets.token_hex(4)
def peer_address(text,port=9009):
    text=text.strip()
    if not text:return ''
    try:
        address=ipaddress.ip_address(text)
    except ValueError:
        match=re.fullmatch(r'(\[[^\]]+\]|[^:]+):([0-9]+)',text)
        if not match:raise ValueError('IPは192.168.1.10、または192.168.1.10:9009のように入力してください。')
        address=ipaddress.ip_address(match[1].strip('[]'));port=int(match[2])
    if not 1<=port<=65535:raise ValueError('接続先ポートは1～65535です。')
    return ('['+str(address)+']' if address.version==6 else str(address))+':'+str(port)
GLOBAL={'local':bool,'no-compress':bool,'internal-dns':bool,'relay':str,'relay6':str,'ip':str,'socks5':str,'connect':str,'throttleUpload':str,'multicast':str,'curve':str}
SEND={'zip':bool,'git':bool,'no-local':bool,'no-multi':bool,'transport':str,'hash':str,'port':int,'transfers':int,'exclude':str,'exclude-file':str}
ENUMS={'curve':('p521','p256','p384','siec','ed25519'),'transport':('auto','derp','relay'),'hash':('xxhash','imohash','md5','highway')}
def validate_options(value):
    if not isinstance(value,dict) or set(value)-{'global','send'}:raise ValueError('設定はglobal/sendのJSONオブジェクトで指定してください。')
    for group,schema in [('global',GLOBAL),('send',SEND)]:
        opts=value.get(group,{})
        if not isinstance(opts,dict):raise ValueError(group+'はオブジェクトです。')
        for key,val in opts.items():
            if key not in schema or type(val)!=schema.get(key):raise ValueError('使えない設定、または型が違います: '+key)
            if isinstance(val,str) and (len(val)>2048 or any(ord(c)<32 for c in val)):raise ValueError('設定値が長すぎるか、制御文字を含んでいます。')
            if key in ENUMS and val not in ENUMS[key]:raise ValueError('使えない値: '+key)
            if key=='port' and not 1024<=val<=65525:raise ValueError('portは1024～65525です。')
            if key=='transfers' and not 1<=val<=8:raise ValueError('transfersは1～8です。')
            if key=='throttleUpload' and not re.fullmatch(r'[1-9][0-9]{0,8}[kKmMgG]?',val):raise ValueError('速度は500kなどで指定してください。')
    g=value.get('global',{});s=value.get('send',{})
    if g.get('local') and (s.get('transport','auto')!='auto' or s.get('no-local')):raise ValueError('LAN専用ではtransport:auto、no-local:falseにしてください。')
    return value
def flags(opts):
    result=[]
    for key,value in opts.items():
        if type(value)==bool:
            if value:result.append('--'+key)
        elif value!='':result+=['--'+key,str(value)]
    return result
import copy

def normalize_network(options):
    o = copy.deepcopy(options)
    g = o.setdefault('global', {})
    s = o.get('send', {})
    g.setdefault('local', True)
    if g['local'] and (s.get('no-local') or s.get('transport', 'auto') != 'auto'):
        raise ValueError("LAN内だけの転送ではno-localを外し、transportをautoにしてください。")
    if not g['local']:
        relay = str(g.get('relay', ''))
        host = relay.split(':')[0].strip().lower().rstrip('.')
        blocked = {'croc.schollz.com', 'croc6.schollz.com', '1.getcroc.com', '2.getcroc.com', '3.getcroc.com', '4.getcroc.com'}
        if not host or host in blocked:
            raise ValueError("標準公開リレーには対応していません。LAN内だけを選ぶか、独自リレーの接続先を指定してください。")
    return o


def arguments(mode,paths=(),options=None):
    opts=normalize_network(validate_options(options or {}))
    args=['--yes','--disable-clipboard','--ignore-stdin',*flags(opts.get('global',{}))]
    if mode=='send':
        if not 1<=len(paths)<=100:raise ValueError('ファイル・フォルダーは1～100件選んでください。')
        items=[]
        for p in paths:
            p=Path(p).resolve(strict=True)
            if not(p.is_file() or p.is_dir()) or p.is_symlink():raise ValueError('通常のファイル・フォルダーを選んでください。')
            items.append(str(p))
        args+=['send',*flags(opts.get('send',{})),'--',*items]
    elif mode=='receive':args+=['--rename']
    else:raise ValueError('送信か受信を選んでください。')
    return args
def transfer(mode,paths,code,destination,options,cancel,note='',relay_password=''):
    code=valid_code(code)
    if not isinstance(relay_password,str) or len(relay_password)>1024 or '\x00' in relay_password:raise ValueError('リレーパスワードが長すぎるか、不正な文字を含みます。')
    if note:
        if mode!='send' or paths:raise ValueError('メモはファイルを選んでいない送信で使います。')
        if len(note.encode('utf8'))>1024*1024:raise ValueError('メモは1 MiBまでです。')
    with tempfile.TemporaryDirectory(prefix='kiwi-transfer-job-') as td:
        work=Path(td)
        if note:
            file=work/'メモ.txt';file.write_text(note,encoding='utf8');paths=[file]
        args=arguments(mode,paths,options)
        receive=None
        if mode=='receive':
            parent=Path(destination).resolve(strict=True)
            if not parent.is_dir():raise ValueError('受信先フォルダーを選んでください。')
            receive=parent/('受信中-'+time.strftime('%Y%m%d-%H%M%S')+'-'+secrets.token_hex(3));receive.mkdir()
            work=receive
        try:log=run_native(native_exe(),args,code,work,cancel,relay_password=relay_password)
        except Exception as e:
            if receive:raise RuntimeError(str(e)+'\n途中のファイルは '+str(receive)+' に残ります。自動では開きません。') from e
            raise
        if receive:
            final=receive.with_name(receive.name.replace('受信中-','受信-',1));receive.rename(final)
        else:final=None
        return {'folder':str(final) if final else '', 'log':log}
