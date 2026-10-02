"""Input handling for JSON path transformations."""
import os,urllib.parse,urllib.request,ssl,base64,time
from pathlib import Path
import runtime

MAX_INPUT=2*1024*1024

def check(cancel,deadline):
    if cancel and cancel.is_set():raise InterruptedError('処理を停止しました。')
    if time.monotonic()>=deadline:raise TimeoutError('処理の時間制限に達しました。')

class Redirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,req,fp,code,msg,headers,newurl):
        destination=urllib.parse.urlsplit(newurl)
        if destination.scheme not in ('http','https'):raise ValueError('HTTP/HTTPS以外への転送は扱えません。')
        new=super().redirect_request(req,fp,code,msg,headers,newurl)
        old=urllib.parse.urlsplit(req.full_url)
        if new and (old.scheme,old.netloc)!=(destination.scheme,destination.netloc):new.remove_header('Authorization')
        return new

def fetch_url(url,insecure,cancel,deadline):
    check(cancel,deadline);parsed=urllib.parse.urlsplit(url)
    headers={'Accept':'application/json','User-Agent':'gron/0.7.1 (KiwiJsonPaths)'}
    if parsed.username is not None:
        credential=urllib.parse.unquote(parsed.username)+':'+urllib.parse.unquote(parsed.password or '')
        headers['Authorization']='Basic '+base64.b64encode(credential.encode('utf8')).decode('ascii')
        host=parsed.hostname
        if ':' in host:host='['+host+']'
        if parsed.port:host+=':'+str(parsed.port)
        url=urllib.parse.urlunsplit((parsed.scheme,host,parsed.path,parsed.query,parsed.fragment))
    context=ssl._create_unverified_context() if insecure else ssl.create_default_context()
    opener=urllib.request.build_opener(Redirects(),urllib.request.HTTPSHandler(context=context))
    parts=[];length=0
    with opener.open(urllib.request.Request(url,headers=headers),timeout=min(20,max(.1,deadline-time.monotonic()))) as response:
        while True:
            check(cancel,deadline);block=response.read(64*1024)
            if not block:break
            length+=len(block)
            if length>MAX_INPUT:raise ValueError('URLの応答は2 MiBまでです。')
            parts.append(block)
    check(cancel,deadline);return b''.join(parts)

def normalize_values(data):
    if not data or len(data)>MAX_INPUT:raise ValueError('抽出入力は2 MiBまでです。')
    # Values in gron use a 64 KiB scanner and otherwise ignore scanner errors.
    raw=runtime._strip_ansi(data.decode('utf8','strict')).encode('utf8')
    lines=[line for line in raw.splitlines() if line.strip()]
    if not lines:raise ValueError('抽出するパス一覧が空です。')
    if any(len(line)>=65535 for line in lines):raise ValueError('値の抽出では1行64 KiB未満の一覧を指定してください。')
    return b'\n'.join(lines)+b'\n'


def build_request(mode, values, paths, text):
    if mode in ("version", "help"):
        return (["--" + mode], None, "")

    if mode not in ("flatten", "restore", "values"):
        raise ValueError("unknown mode")

    url_str = str(values.get("@url") or "").strip()
    if any(v is not None and "\0" in v for v in (text,url_str,*paths)):
        raise ValueError("NUL文字は許可されていません。")
    has_text = bool(text and text.strip())
    # Validate options
    stream = bool(values.get("--stream", False))
    json_flag = bool(values.get("--json", False))
    no_sort = bool(values.get("--no-sort", False))
    color = values.get("@color", None)
    insecure = bool(values.get("--insecure", False))

    if stream and mode != "flatten":
        raise ValueError("--stream only for flatten")
    if json_flag:
        if mode == "values":
            raise ValueError("--json ignored/rejected in values mode")
    if no_sort and mode != "flatten":
        raise ValueError("--no-sort only for flatten")

    # Color handling
    color_args = []
    if color is not None:
        if color == "monochrome":
            color_args.append("--monochrome")
        elif color == "colorize":
            if mode == "values":
                raise ValueError("colorize rejected in values mode")
            color_args.append("--colorize")
        else:
            raise ValueError("invalid color choice")

    # Source validation
    source_count = 0
    stdin_data = None
    positional = []

    if has_text:
        source_count += 1
        if len(text.encode('utf-8')) > 2 * 1024 * 1024:
            raise ValueError("text exceeds 2MiB")
        stdin_data = text.encode('utf-8')

    for p in paths:
        p = os.path.abspath(p)
        source_count += 1
        if os.path.isdir(p):
            raise ValueError("directory not allowed")
        if not os.path.isfile(p):
            raise ValueError("file does not exist")
        size = os.path.getsize(p)
        if size > 20 * 1024 * 1024:
            raise ValueError("file exceeds 20MiB")
        positional.append(p)

    if url_str:
        source_count += 1
        parsed = urllib.parse.urlparse(url_str)
        if parsed.scheme not in ("http", "https"):
            raise ValueError("invalid URL scheme")
        if parsed.port is not None and not 1 <= parsed.port <= 65535:
            raise ValueError("ポート番号は1〜65535です。")
        if not parsed.hostname:
            raise ValueError("missing hostname")
        if any(c.isspace() or ord(c) < 32 for c in url_str):
            raise ValueError("whitespace/control in URL")
        positional.append(url_str)

    if source_count != 1:
        raise ValueError("exactly one source required")

    # Build args
    args = []

    if mode == "flatten":
        pass  # default, no flag needed
    elif mode == "restore":
        args.append("--ungron")
    elif mode == "values":
        args.append("--values")

    if stream:
        args.append("--stream")
    if json_flag:
        args.append("--json")
    if no_sort:
        args.append("--no-sort")

    args.extend(color_args)

    # Insecure only for URL
    if insecure:
        if not url_str:
            raise ValueError("--insecure requires URL")
        args.append("--insecure")

    # Extension logic
    extension = ""
    if mode == "flatten":
        extension = ".jsonl" if json_flag else ".gron"
    elif mode == "restore":
        extension = ".json"
    elif mode == "values":
        extension = ".txt"

    # Handle values mode with file source: read into stdin
    if mode == "values" and paths and not has_text and not url_str:
        with open(paths[0], 'rb') as f:
            data = f.read(MAX_INPUT + 1)
        if len(data) > 2 * 1024 * 1024:
            raise ValueError("file exceeds 2MiB for values stdin")
        stdin_data = data
        positional = []  # no positional for file in values mode

    # Add '--' before positional args (URL/file)
    if positional:
        args.append("--")
        args.extend(positional)

    return (args, stdin_data, extension)


def execute_job(exe, mode, values, paths, text, cancel_event):
    deadline = time.monotonic() + 300
    check(cancel_event, deadline)
    args, data, extension = build_request(mode, values, paths, text)

    if mode not in ("help", "version") and str(values.get("@url") or "").strip():
        url = str(values["@url"]).strip()
        insecure = bool(values.get("--insecure", False))
        data = fetch_url(url, insecure, cancel_event, deadline)
        if "--" in args:
            args = args[:args.index("--")]
        if "--insecure" in args:
            args.remove("--insecure")

    check(cancel_event, deadline)
    remaining = max(0.1, deadline - time.monotonic())

    if mode == "values":
        data = normalize_values(data)
        result = runtime.execute(exe, ["--ungron", "--monochrome"], stdin_data=data, cancel_event=cancel_event, timeout=remaining, max_output=16777216)
        if result["returncode"] != 0:
            result["extension"] = ".txt"
            return result

    check(cancel_event, deadline)
    remaining = max(0.1, deadline - time.monotonic())
    result = runtime.execute(exe, args, stdin_data=data, cancel_event=cancel_event, timeout=remaining, max_output=16777216)

    if mode == "help" and result["returncode"] == 0:
        if not result["stdout"]:
            result["stdout"] = result["stderr"]
            result["stderr"] = b""

    result["extension"] = extension
    return result
