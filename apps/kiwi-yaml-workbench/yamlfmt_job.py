"""Bounded staging and CLI execution for YAML inputs."""
import os,sys,json,hashlib,tempfile,time,zipfile,io,threading
from pathlib import Path
import runtime

MAX_OUTPUT=16*1024*1024
MAX_TREE=64*1024*1024

def execute_stage(exe,args,stage,cancel,deadline):
    from workbench_jobs import _monitor_dir_size
    check(cancel,deadline)
    cancel=cancel or threading.Event();stop=threading.Event()
    monitor=_monitor_dir_size(stage,stop,cancel)
    try:
        return runtime.execute(exe,args,stdin_data=None,cwd=str(stage),cancel_event=cancel,
                               timeout=max(.1,deadline-time.monotonic()),max_output=MAX_OUTPUT)
    finally:
        stop.set();monitor.join(timeout=2)

def check(cancel,deadline):
    if cancel and cancel.is_set():raise InterruptedError('処理を停止しました。')
    if time.monotonic()>deadline:raise TimeoutError('300秒の時間制限に達しました。')

def safe_path(path):
    path=Path(path).absolute()
    for p in [path,*path.parents]:
        if p.is_symlink() or p.is_junction():raise ValueError('リンク・ジャンクションを含む入力は扱えません。')
    return path

def relative_pattern(value,anchored=False):
    value=str(value).replace('\\','/')
    if anchored:value=value.lstrip('!').lstrip('/')
    if not value or ':' in value or value.startswith('/') or '..' in value.split('/') or '\x00' in value:
        raise ValueError('パターンは対象内の相対パスで指定してください。')
    return value

def stage_input(stage,paths,data,cancel,deadline):
    snapshot={};count=0;size=0;dirs=0
    def copy_file(src,dst):
        nonlocal count,size
        check(cancel,deadline);safe_path(src)
        if not src.is_file():raise ValueError('通常のファイルを指定してください。')
        count+=1
        if count>2000 or size+src.stat().st_size>MAX_TREE:raise ValueError('入力は2000ファイル・合計64 MiBまでです。')
        dst.parent.mkdir(parents=True,exist_ok=True)
        with src.open('rb') as read,dst.open('xb') as write:
            total=0
            while block:=read.read(1024*1024):
                check(cancel,deadline);total+=len(block);size+=len(block)
                if size>MAX_TREE:raise ValueError('入力は合計64 MiBまでです。')
                if total>src.stat().st_size or total>MAX_TREE:raise ValueError('コピー中に入力サイズが変わりました。')
                write.write(block)
        snapshot[dst.relative_to(stage).as_posix()]=hashlib.sha256(dst.read_bytes()).hexdigest()
    if data:
        if len(data)>2*1024*1024:raise ValueError('入力テキストは2 MiBまでです。')
        (stage/'input.yaml').write_bytes(data);selected=['input.yaml']
        snapshot['input.yaml']=hashlib.sha256(data).hexdigest()
    else:
        inputs=list(dict.fromkeys(safe_path(p) for p in paths))
        if not inputs:raise ValueError('対象を指定してください。')
        for p in inputs:
            if not p.exists():raise ValueError('対象が見つかりません。')
        # A selected directory subsumes its selected descendants.
        inputs=[p for p in inputs if not any(q!=p and q.is_dir() and p.is_relative_to(q) for q in inputs)]
        common=Path(os.path.commonpath([str(p if p.is_dir() else p.parent) for p in inputs]))
        selected=[]
        for p in inputs:
            rel=p.relative_to(common);selected.append(rel.as_posix())
            if p.is_file():copy_file(p,stage/rel);continue
            def walk_error(error):raise error
            for root,names,files in os.walk(p,followlinks=False,onerror=walk_error):
                check(cancel,deadline);dirs+=1
                if dirs>2000:raise ValueError('フォルダーは2000個までです。')
                for name in names:safe_path(Path(root)/name)
                for name in files:
                    src=Path(root)/name;copy_file(src,stage/src.relative_to(common))
    (stage.parent/'snapshot.json').write_text(json.dumps(snapshot),encoding='utf8')
    return selected

def validate_selection(stage,config_json,args,patterns,selected):
    config=json.loads(config_json or '{}');effective=config.get('match_type','doublestar' if config.get('doublestar') else 'standard')
    parsed={};i=0
    value_flags={'-match_type','-exclude','-extensions','-gitignore_path','-output_format','-debug','-formatter'}
    allowed=value_flags|{'-gitignore_excludes','-continue_on_error','-quiet','-verbose'}
    while i<len(args):
        flag=args[i]
        if flag not in allowed:raise ValueError('未対応の実行オプションです。')
        if flag in value_flags:
            if i+1>=len(args):raise ValueError('オプション値が不足しています。')
            parsed.setdefault(flag,[]).append(args[i+1]);i+=2
        else:parsed[flag]=True;i+=1
    if parsed.get('-match_type'):effective=parsed['-match_type'][-1]
    if effective not in ('standard','doublestar','gitignore'):raise ValueError('検索方法が無効です。')
    pos=[relative_pattern(line.strip()) for line in patterns.splitlines() if line.strip()]
    if not pos:
        pos=['yamlfmt.patterns'] if effective=='gitignore' else list(selected)
    for pattern in pos:relative_pattern(pattern)
    ignore_path=parsed.get('-gitignore_path',['.gitignore'])[-1]
    ignore_path=relative_pattern(ignore_path)
    ignore_files=list(pos) if effective=='gitignore' else []
    if parsed.get('-gitignore_excludes') or config.get('gitignore_excludes'):ignore_files.append(ignore_path)
    for name in ignore_files:
        p=safe_path(stage/name)
        if not p.is_relative_to(stage) or not p.is_file() or p.stat().st_size>128*1024:raise ValueError('対象内のパターンファイル（128 KiBまで）を指定してください。')
        for line in p.read_text(encoding='utf-8-sig').splitlines():
            line=line.strip()
            if line and not line.startswith('#'):relative_pattern(line,anchored=True)
    # Explicit path also overrides an absolute gitignore_path in a config.
    safe_args=[];i=0
    while i<len(args):
        f=args[i]
        if f=='-gitignore_path':i+=2;continue
        safe_args.append(f)
        if f in value_flags:safe_args.append(args[i+1]);i+=2
        else:i+=1
    safe_args+=['-gitignore_path',ignore_path]
    return safe_args,pos

def make_result_zip(stage,cancel,deadline):
    snapshot=json.loads((stage.parent/'snapshot.json').read_text(encoding='utf8'))
    buf=io.BytesIO();size=0;changed=[]
    with zipfile.ZipFile(buf,'w',zipfile.ZIP_DEFLATED) as archive:
        for name,before in snapshot.items():
            check(cancel,deadline);p=stage/name
            size+=p.stat().st_size
            if size>MAX_TREE:raise ValueError('整形結果は合計64 MiBまでです。')
            b=p.read_bytes()
            if hashlib.sha256(b).hexdigest()!=before:
                archive.writestr(name,b);changed.append(name)
                if buf.tell()>MAX_OUTPUT:raise ValueError('ZIPは16 MiBまでです。')
    return buf.getvalue()


def execute_job(exe, args, stdin_data, cancel_event, mode, paths, config_text='', patterns=''):
    deadline = time.monotonic() + 300
    if mode in ('version', 'help'):
        flag = '-version' if mode == 'version' else '-help'
        r = runtime.execute(exe, [flag], None, None, cancel_event, 10, MAX_OUTPUT)
        return {"stdout": r["stdout"], "stderr": r["stderr"], "returncode": r["returncode"], "extension": ""}

    if mode not in ('format', 'dry', 'lint', 'config'):
        raise ValueError(f"Invalid mode: {mode}")

    has_paths = bool(paths)
    has_text = bool(stdin_data)
    if mode in ('format', 'dry', 'lint') and has_paths and has_text:
        raise ValueError("Cannot mix paths and text input")
    if mode in ('format', 'dry', 'lint') and not has_paths and not has_text:
        raise ValueError("No input provided")

    with tempfile.TemporaryDirectory(prefix='kiwi-yamlfmt-') as td:
        root = Path(td)
        stage = root / "stage"
        stage.mkdir()

        conf_path = root / "conf.json"
        if config_text:
            conf_path.write_text(config_text, encoding="utf-8")
        else:
            conf_path.write_text("{}", encoding="utf-8")

        safe_args = []
        safe_positional = []
        selected = []

        if mode in ('format', 'dry', 'lint'):
            if has_text and mode == 'format':
                # Early branch for text format to avoid writing/truncating input.yaml
                remaining = max(0.1, deadline - time.monotonic())
                check(cancel_event, deadline)
                try:
                    r = runtime.execute(exe, ['-conf', str(conf_path), '-in'] + args, stdin_data=stdin_data, cwd=str(stage), cancel_event=cancel_event, timeout=remaining, max_output=MAX_OUTPUT)
                except (InterruptedError, TimeoutError):
                    raise
                return {
                    "stdout": r["stdout"],
                    "stderr": r["stderr"],
                    "returncode": r["returncode"],
                    "extension": ".yaml"
                }
            else:
                selected = stage_input(stage, paths, stdin_data, cancel_event, deadline)

            safe_args, safe_positional = validate_selection(stage, config_text, args, patterns, selected)

        if mode == 'config':
            # Include command-level options when displaying the merged configuration.
            cli_args = ['-conf', str(conf_path), '-print_conf'] + args
        elif mode in ('format', 'dry', 'lint'):
            mode_flag = {'format': [], 'dry': ['-dry'], 'lint': ['-lint']}[mode]
            cli_args = ['-conf', str(conf_path)] + safe_args + mode_flag + safe_positional

        remaining = max(0.1, deadline - time.monotonic())
        check(cancel_event, deadline)

        try:
            r = execute_stage(exe,cli_args,stage,cancel_event,deadline)
        except (InterruptedError, TimeoutError):
            raise

        stdout, stderr, rc = r["stdout"], r["stderr"], r["returncode"]

        has_differences = False
        if mode == 'lint' and rc == 1:
            # Keep lint differences available for report saving without accepting parse errors.
            if stderr.startswith(b'The following formatting differences were found:'):
                stdout = stderr
                stderr = b""
                has_differences = True

        result = {
            "stdout": stdout,
            "stderr": stderr,
            "returncode": rc,
            "extension": ""
        }

        # Set extension.txt for dry/lint/config
        if mode in ('dry', 'lint', 'config'):
            result["extension"] = ".txt"

        if mode == 'lint' and has_differences:
            result['status'] = 'differences'

        if mode == 'format' and not has_text and rc == 0:
            zip_bytes = make_result_zip(stage, cancel_event, deadline)
            if stdout:
                result['stderr'] = stderr + b'\n' + stdout
            if len(zip_bytes) + len(result['stderr']) > MAX_OUTPUT:
                raise ValueError('出力は合計16 MiBまでです。')
            result["stdout"] = zip_bytes
            result["extension"] = ".zip"
            result["display"] = "内容が変わったファイルだけを含むZIPです。変更がなければ空になります。"

        return result
