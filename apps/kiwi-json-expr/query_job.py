"""Prepare bounded local inputs for gojq queries."""
import os,time,json,tempfile
from pathlib import Path
import runtime

def read_path(value,limit=20*1024*1024):
    if not value or '\0' in value:raise ValueError('ファイルのパスを指定してください。')
    p=Path(value).expanduser().absolute()
    if any(x.is_symlink() or x.is_junction() for x in (p,*p.parents)):raise ValueError('リンクは入力に使えません。')
    if not p.is_file() or p.stat().st_size>limit:raise ValueError('ファイルが見つからないか、容量の上限を超えています。')
    return str(p)

def input_source(paths,text):
    if paths and text.strip():raise ValueError('テキストとファイルは同時に指定できません。')
    if len(text.encode('utf8'))>2*1024*1024:raise ValueError('入力テキストは2 MiBまでです。')
    if len(paths)>200:raise ValueError('ファイルは200件までです。')
    files=[read_path(str(p)) for p in paths]
    if sum(Path(p).stat().st_size for p in files)>64*1024*1024:raise ValueError('ファイルは合計64 MiBまでです。')
    return files,None if files else text.encode('utf8')

def json_field(value,expected):
    if len(value.encode('utf8'))>128*1024:raise ValueError('変数設定は128 KiBまでです。')
    data=json.loads(value or ('{}' if expected is dict else '[]'),parse_constant=lambda x:(_ for _ in ()).throw(ValueError('JSONの数値が不正です。')))
    if not isinstance(data,expected):raise ValueError('変数はJSONオブジェクト、位置引数はJSON配列で指定してください。')
    return data

def build_request(mode, values, paths, text):
    if mode in ("help", "version"):
        return (["--" + mode], None, ".txt")
    if mode != "query":
        raise ValueError("不明なモードです。")
    args = []
    v = lambda k: str(values.get(k, "")).strip()

    # Input format
    inp = v("@input")
    if inp == "yaml": args.append("--yaml-input")
    elif inp == "raw": args.append("--raw-input")
    elif inp == "stream": args.append("--stream")
    elif inp != "json": raise ValueError("入力形式が不正です。")

    # Output format
    out = v("@output")
    ext = ".json"
    if out == "yaml": args.append("--yaml-output"); ext = ".yaml"
    elif out == "raw": args.extend(["--raw-output"]); ext = ".txt"
    elif out == "raw0": args.extend(["--raw-output0"]); ext = ".txt"
    elif out == "join": args.extend(["--join-output"]); ext = ".txt"
    elif out != "json": raise ValueError("出力形式が不正です。")

    # Bool flags
    for f in ("--slurp", "--null-input", "--exit-status", "--compact-output", "--tab"):
        if values.get(f): args.append(f)

    # Indent
    ind_s = v("--indent")
    if ind_s:
        try: ind = int(ind_s)
        except ValueError: raise ValueError("字下げの幅は整数で指定してください。")
        if not 0 <= ind <= 9: raise ValueError("字下げの幅は0から9までです。")
        args.extend(["--indent", str(ind)])

    # Color
    col = v("@color") or 'mono'
    if col == "mono": args.append("--monochrome-output")
    elif col == "color": args.append("--color-output")
    else: raise ValueError("出力の色が不正です。")

    # Query source: --from-file or @filter
    from_file = v("--from-file")
    query_arg = None
    if from_file:
        # Read path but do not add to args yet; will be added after '--'
        query_arg = read_path(from_file, limit=2*1024*1024)
    else:
        raw_filter = values.get('@filter')
        if raw_filter is None:
            filt = "."
        else:
            filt = str(raw_filter).strip()
            if not filt: raise ValueError("式が空です。")
        if len(filt.encode('utf-8')) > 65536 or '\0' in filt:
            raise ValueError("式が長すぎます。")
        query_arg = filt

    # Module paths (-L)
    mod_raw = v("-L")
    if mod_raw:
        dirs = [d.strip() for d in mod_raw.splitlines() if d.strip()]
        if len(dirs) > 32: raise ValueError("モジュールフォルダーは32件までです。")
        for d in dirs:
            if '\0' in d: raise ValueError("パスにNUL文字が含まれています。")
            p = Path(d).expanduser().absolute()
            if any(x.is_symlink() or x.is_junction() for x in (p, *p.parents)):
                raise ValueError("リンクはモジュールフォルダーに使えません。")
            if not p.is_dir(): raise ValueError("モジュールフォルダーが見つかりません。")
            args.extend(["-L", str(p)])

    # Named variables: @strings, @json, @slurpfiles, @rawfiles
    named_count = 0
    def add_named(flag, name, val):
        nonlocal named_count
        if not name or len(name) > 128 or '\0' in name: raise ValueError("変数名が不正です。")
        if '\0' in str(val): raise ValueError("値にNUL文字が含まれています。")
        args.extend([flag, name, str(val)])
        named_count += 1

    for key in ("@strings", "@json", "@slurpfiles", "@rawfiles"):
        data = json_field(v(key), dict)
        for k, val in data.items():
            if key == "@strings":
                if not isinstance(val, str): raise ValueError("文字列変数は文字列で指定してください。")
                add_named("--arg", k, val)
            elif key == "@json":
                try: jv = json.dumps(val, ensure_ascii=False, allow_nan=False)
                except (TypeError, ValueError): raise ValueError("JSON変数の値が不正です。")
                add_named("--argjson", k, jv)
            elif key == "@slurpfiles":
                if not isinstance(val, str): raise ValueError("ファイルパスは文字列で指定してください。")
                add_named("--slurpfile", k, read_path(val, limit=2*1024*1024))
            elif key == "@rawfiles":
                if not isinstance(val, str): raise ValueError("ファイルパスは文字列で指定してください。")
                add_named("--rawfile", k, read_path(val, limit=2*1024*1024))

    if named_count > 100: raise ValueError("変数は合計100件までです。")

    # Positional args: @positional + @args
    pos_data = json_field(v("@positional"), list)
    if len(pos_data) > 100: raise ValueError("位置引数は100件までです。")
    arg_type = v("@args") or "strings"
    positions = []
    if arg_type == "json":
        for item in pos_data:
            try: jv = json.dumps(item, ensure_ascii=False, allow_nan=False)
            except (TypeError, ValueError): raise ValueError("位置引数のJSONが不正です。")
            positions.append(jv)
    elif arg_type == "strings":
        for item in pos_data:
            if not isinstance(item, str): raise ValueError("文字列位置引数はすべて文字列で指定してください。")
            if '\0' in item: raise ValueError("値にNUL文字が含まれています。")
            positions.append(item)
    else: raise ValueError("位置引数の種類が不正です。")

    # Input files vs stdin
    files, stdin_bytes = input_source(paths, text)

    # Ambiguity check: positional args + input files
    has_positional = bool(pos_data)
    if has_positional and files:
        raise ValueError("位置引数と入力ファイルは同時に指定できません。")

    # Final assembly order: flags -> named vars -> positional flag -> '--' -> query -> files -> positions
    if from_file:
        args.append("--from-file")

    if has_positional:
        args.append("--jsonargs" if arg_type == "json" else "--args")

    args.append('--')
    args.append(query_arg)
    args.extend(files)
    args.extend(positions)

    return (args, stdin_bytes, ext)

def execute_job(exe, mode, values, paths, text, cancel_event):
    if cancel_event.is_set(): raise InterruptedError('キャンセルされました。')
    deadline = time.monotonic() + 300
    args, stdin_data, extension = build_request(mode, values, paths, text)
    remaining = deadline - time.monotonic()
    if remaining <= 0: raise TimeoutError('準備に時間がかかりすぎました。')
    if cancel_event.is_set(): raise InterruptedError('キャンセルされました。')
    with tempfile.TemporaryDirectory(prefix='gojq_') as tmp:
        result = runtime.execute(exe, args, stdin_data, cwd=tmp, cancel_event=cancel_event, timeout=remaining, max_output=16777216)
    stdout = result['stdout'];stderr = result['stderr'];rc = result['returncode']
    if mode in ("help", "version"):
        display = runtime._strip_ansi(stdout.decode('utf-8', 'replace'))[:131072]
    else:
        display = runtime._strip_ansi(stdout.decode('utf-8', 'replace'))[:131072]
        if rc == 0: prefix = '処理完了。\n'
        elif rc in (1, 4): prefix = f'終了状態 (rc={rc})。出力と診断を確認してください。\n'
        else: prefix = f'実行失敗 (rc={rc})\n'
        display = prefix + display
    return {'stdout':stdout,'stderr':stderr,'returncode':rc,'extension':extension,'display':display[:131072]}
