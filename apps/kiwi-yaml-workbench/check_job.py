"""Bounded local workflow inputs for the bundled actionlint."""
import os,time,tempfile,json
from pathlib import Path
import runtime
MAX_INPUT=2*1024*1024

def check(cancel,deadline):
    if cancel and cancel.is_set():raise InterruptedError('処理を停止しました。')
    if time.monotonic()>=deadline:raise TimeoutError('処理の時間制限に達しました。')

def sources(paths,text,cancel,deadline):
    if text and text.strip():
        if paths:raise ValueError('テキストとファイルは同時に指定できません。')
        if len(text.encode('utf8'))>MAX_INPUT:raise ValueError('入力テキストは2 MiBまでです。')
        return [],text.encode('utf8')
    if not paths:raise ValueError('ワークフローのテキスト、ファイル、フォルダーを指定してください。')
    found=[];seen=set();size=0;dirs=0
    def add(p):
        nonlocal size
        check(cancel,deadline)
        if p.is_symlink() or p.is_junction():raise ValueError('リンクは入力に使えません。')
        if not p.is_file():raise ValueError('入力ファイルが見つかりません。')
        resolved=p.resolve();identity=os.path.normcase(str(resolved))
        if identity in seen:return
        n=resolved.stat().st_size
        if n>20*1024*1024:raise ValueError('1ファイルは20 MiBまでです。')
        size+=n
        if size>64*1024*1024 or len(found)>=200:raise ValueError('入力は200ファイル・合計64 MiBまでです。')
        seen.add(identity);found.append(str(resolved))
    for value in paths:
        if '\0' in str(value):raise ValueError('NUL文字は入力に使えません。')
        p=Path(value).absolute()
        if p.is_symlink() or p.is_junction():raise ValueError('リンクは入力に使えません。')
        if p.is_dir():
            workflows=p/'.github/workflows';base=workflows if workflows.is_dir() else p
            stack=[base]
            while stack:
                folder=stack.pop();check(cancel,deadline);dirs+=1
                if dirs>2000:raise ValueError('探索は2000フォルダーまでです。')
                if folder.is_symlink() or folder.is_junction():continue
                for child in sorted(folder.iterdir()):
                    if child.is_symlink() or child.is_junction():continue
                    if child.is_dir():stack.append(child)
                    elif child.suffix.lower() in ('.yml','.yaml'):add(child)
        else:add(p)
    if not found:raise ValueError('YAMLファイルが見つかりません。')
    return sorted(found),None

def build_args(mode, values, config_path):
    if mode == "help": return ["-help"], ".txt"
    if mode == "version": return ["-version"], ".txt"
    if mode == "init": return ["-init-config"], ".yaml"
    if mode not in ("lint", "json", "custom"): raise ValueError("unknown mode")

    def vext(name):
        val = values.get(name, "")
        if not val:
            return ""
        if "\x00" in val:
            raise ValueError(f"invalid {name}")
        p = Path(os.path.expanduser(val))
        if not (p.is_absolute() and p.is_file() and p.suffix.lower() == ".exe"):
            raise ValueError(f"invalid {name}")
        return str(p)

    args = ["-shellcheck", vext("-shellcheck"), "-pyflakes", vext("-pyflakes"), "-config-file", config_path]

    if mode == "json":
        args.extend(["-format", "{{json .}}"])
    elif mode == "custom":
        tpl = values.get("-format", "")
        if not tpl or len(tpl) > 8192: raise ValueError("invalid template")
        if "\x00" in tpl: raise ValueError("invalid template")
        args.extend(["-format", tpl])

    patterns = [p.strip() for p in (values.get("-ignore", "") or "").splitlines() if p.strip()]
    if len(patterns) > 100:
        raise ValueError("ignore patterns limit is 100")
    for p in patterns:
        if len(p) > 1024:
            raise ValueError("invalid ignore pattern")
        if "\x00" in p:
            raise ValueError("invalid ignore pattern")
        args.extend(["-ignore", p])

    if values.get("-oneline"): args.append("-oneline")

    color = values.get("@color", "no-color") or "no-color"
    if color == "color":
        args.append("-color")
    elif color == "no-color":
        args.append("-no-color")
    else:
        raise ValueError("invalid color option")

    sf = values.get("-stdin-filename", "workflow.yaml") or "workflow.yaml"
    if "\x00" in sf or len(sf) > 1024: raise ValueError("invalid stdin filename")
    args.extend(["-stdin-filename", sf])

    return args, ".json" if mode == "json" else ".txt"

def execute_job(exe, mode, values, paths, text, cancel_event):
    deadline = time.monotonic() + 300
    check(cancel_event, deadline)
    MAX_DISPLAY = 131072
    with tempfile.TemporaryDirectory(prefix="actionlint_") as tmp:
        cwd = Path(tmp)
        if mode == "init":
            (cwd / ".git").mkdir(parents=True, exist_ok=True)
            (cwd / ".github" / "workflows").mkdir(parents=True, exist_ok=True)
            args, ext = build_args(mode, {}, "")
            check(cancel_event, deadline)
            remaining = max(0.1, deadline - time.monotonic())
            res = runtime.execute(exe, args, None, str(cwd), cancel_event, remaining, 16777216)
            if res["returncode"] == 0:
                cfg_path = cwd / ".github" / "actionlint.yaml"
                if not cfg_path.is_file():
                    raise ValueError("init did not produce config file")
                with cfg_path.open("rb") as handle:
                    data = handle.read(131073)
                if len(data) > 131072:
                    raise ValueError("config exceeds 128 KiB")
                res["stdout"] = data
            return {"returncode": res["returncode"], "stdout": res["stdout"], "stderr": res["stderr"], "extension": ext, "display": runtime._strip_ansi(res["stdout"].decode("utf8", "replace"))[:MAX_DISPLAY]}

        if mode in ("help", "version"):
            args, ext = build_args(mode, {}, "")
            check(cancel_event, deadline)
            remaining = max(0.1, deadline - time.monotonic())
            res = runtime.execute(exe, args, None, str(cwd), cancel_event, remaining, 16777216)
            if res["returncode"] == 0 and not res["stdout"]:
                res["stdout"] = res["stderr"]
                res["stderr"] = b""
            return {"returncode": res["returncode"], "stdout": res["stdout"], "stderr": res["stderr"], "extension": ext, "display": runtime._strip_ansi(res["stdout"].decode("utf8", "replace"))[:MAX_DISPLAY]}

        cfg_str = str(values.get("@config") or "")
        if not cfg_str.strip():
            cfg_str = "{}\n"
        cfg_bytes = cfg_str.encode("utf8")
        if len(cfg_bytes) > 131072:
            raise ValueError("config exceeds 128 KiB")
        if b"\x00" in cfg_bytes:
            raise ValueError("NUL in config")
        cfg_file = cwd / "actionlint.yaml"
        cfg_file.write_bytes(cfg_bytes)

        files, stdin_data = sources(paths, text, cancel_event, deadline)
        args, ext = build_args(mode, values, str(cfg_file))

        res = run_checks(exe, mode, args, files, stdin_data, cwd, cancel_event, deadline)

        rc = res["returncode"]
        out_text = res["stdout"].decode("utf8", "replace")
        stripped = runtime._strip_ansi(out_text)

        if rc == 0:
            prefix = "指摘なし。\n"
        elif rc == 1:
            prefix = "指摘あり。\n"
        else:
            prefix = f"実行失敗 (rc={rc})\n"

        display = (prefix + stripped)[:MAX_DISPLAY]
        return {"returncode": rc, "stdout": res["stdout"], "stderr": res["stderr"], "extension": ext, "display": display}

def run_checks(exe, mode, args, files, stdin_data, temp_cwd, cancel_event, deadline):
    check(cancel_event, deadline)
    if not isinstance(args, list) or any(not isinstance(a, str) for a in args):
        raise ValueError("args must be a list of strings")

    def _group_root(p: Path) -> Path:
        cur = p.parent
        while True:
            check(cancel_event, deadline)
            if (cur / ".git").exists() and (cur / ".github" / "workflows").is_dir():
                return cur
            nxt = cur.parent
            if nxt == cur:
                break
            cur = nxt
        return p.parent

    groups = {}
    for f in files or []:
        fp = Path(f)
        root = _group_root(fp)
        rel = str(fp.relative_to(root))
        groups.setdefault(str(root), []).append(rel)

    results = []
    total_size = 0
    max_rc = 0

    for root, rels in sorted(groups.items()):
        check(cancel_event, deadline)
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError("処理の時間制限に達しました。")
        res = runtime.execute(str(exe), list(args) + ["--", *rels], None, root, cancel_event, remaining, 16777216)
        rc = res["returncode"]
        out = bytes(res.get("stdout") or b"")
        err = bytes(res.get("stderr") or b"")
        total_size += len(out) + len(err)
        if total_size > 16 * 1024 * 1024:
            raise ValueError("出力が16 MiBを超えました。")
        max_rc = max(max_rc, rc)
        results.append((rc, out, err))

    if stdin_data is not None:
        check(cancel_event, deadline)
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError("処理の時間制限に達しました。")
        res = runtime.execute(str(exe), list(args) + ["-"], bytes(stdin_data), str(temp_cwd), cancel_event, remaining, 16777216)
        rc = res["returncode"]
        out = bytes(res.get("stdout") or b"")
        err = bytes(res.get("stderr") or b"")
        total_size += len(out) + len(err)
        if total_size > 16 * 1024 * 1024:
            raise ValueError("出力が16 MiBを超えました。")
        max_rc = max(max_rc, rc)
        results.append((rc, out, err))

    if not results:
        raise ValueError("入力がありません。")
    max_rc = next((r[0] for r in results if r[0] < 0), max(r[0] for r in results))
    all_out = b"".join(r[1] for r in results)
    all_err = b"".join(r[2] for r in results)

    if mode == "json":
        if any(rc not in (0, 1) for rc, _, _ in results):
            return {"stdout": all_out, "stderr": all_err, "returncode": max_rc}
        merged = []
        for rc, out, err in results:
            data = json.loads(out.decode("utf-8"))
            if not isinstance(data, list):
                raise ValueError("JSON output is not a list")
            merged.extend(data)
        payload = json.dumps(merged, ensure_ascii=False).encode("utf-8") + b"\n"
        if len(payload) + len(all_err) > 16 * 1024 * 1024:
            raise ValueError("JSON merged output exceeds 16 MiB")
        return {"stdout": payload, "stderr": all_err, "returncode": max_rc}

    return {"stdout": all_out, "stderr": all_err, "returncode": max_rc}
