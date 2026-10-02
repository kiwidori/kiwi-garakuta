import runtime
from pathlib import Path
import os
import json
import base64
from typing import List, Dict, Any

MAX_DISPLAY = 1000
MAX_SCOPE = 200
MAX_QUERY_BYTES = 4096
MAX_DEPTH = 1000
MAX_CONTEXT = 1000
MAX_COUNT = 1000000
MAX_EXCLUDES = 32
MAX_EXTENSIONS = 16

def _is_link_or_ancestor_link(path: str) -> bool:
    p=Path(path).absolute()
    return any(part.is_symlink() or part.is_junction() for part in [p,*p.parents])

def _validate_folder(folder: str) -> None:
    abs_folder = os.path.abspath(folder)
    if not os.path.isdir(abs_folder):
        raise ValueError("Folder must be an existing directory")
    if _is_link_or_ancestor_link(abs_folder):
        raise ValueError("Symlinks or junctions in folder path are rejected")

def _validate_query(pattern: str, engine: str) -> None:
    if '\x00' in pattern:
        raise ValueError("Pattern must not contain NUL")
    b = pattern.encode('utf-8')
    if len(b) > MAX_QUERY_BYTES:
        raise ValueError("Pattern exceeds 4096 UTF-8 bytes")
    if engine == 'rg' and not pattern:
        raise ValueError("Ripgrep requires a non-empty pattern to avoid giant scans")

def _parse_int(val: str, name: str, min_val: int, max_val: int) -> int:
    try:
        n = int(val)
    except (ValueError, TypeError):
        raise ValueError(f"{name} must be an integer")
    if n < min_val or n > max_val:
        raise ValueError(f"{name} out of bounds [{min_val}, {max_val}]")
    return n

def _parse_extensions(extensions: str) -> List[str]:
    exts = []
    for line in extensions.replace('\n', ',').split(','):
        e = line.strip()
        if not e:
            continue
        if e.startswith('.'):
            e = e[1:]
        if '/' in e or '\\' in e or '\x00' in e or any(c in e for c in '*?[]{}') or not e:
            raise ValueError(f"Invalid extension: {e}")
        exts.append(e)
    if len(exts) > MAX_EXTENSIONS:
        raise ValueError("Too many extensions (max 16)")
    return exts

def _parse_excludes(excludes: str) -> List[str]:
    globs = []
    for line in excludes.split('\n'):
        g = line.strip()
        if not g:
            continue
        if g.startswith('!') or '\x00' in g:
            raise ValueError("Excludes must not start with '!' or contain NUL")
        globs.append(g)
    if len(globs) > MAX_EXCLUDES:
        raise ValueError("Too many excludes (max 32)")
    return globs

def _build_fd_args(options: dict, folder: str) -> List[str]:
    args = ["--absolute-path", "--print0", "--color", "never", "--type", "file"]
    mode = options.get('pattern_mode', 'literal')
    if mode == 'literal':
        args.append("--fixed-strings")
    elif mode == 'glob':
        args.append("--glob")

    if options.get('full_path'):
        args.append("--full-path")

    case = options.get('case', 'auto')
    if case == 'sensitive':
        args.append("--case-sensitive")
    elif case == 'ignore':
        args.append("--ignore-case")

    if options.get('hidden'):
        args.append("--hidden")
    if options.get('ignored'):
        args.append("--no-ignore")

    depth = options.get('depth')
    if depth:
        d = _parse_int(depth, "depth", 1, MAX_DEPTH)
        args.extend(["--max-depth", str(d)])

    for g in _parse_excludes(options.get('excludes', '')):
        args.append("--exclude="+g)

    for e in _parse_extensions(options.get('extensions', '')):
        args.append("--extension="+e)

    args.extend(["--", options['pattern'], folder])
    return args

def _build_rg_args(options: dict, scope_paths: List[str], folder: str) -> List[str]:
    args = ["--no-config", "--json", "--line-number", "--color", "never", "--crlf"]
    mode = options.get('pattern_mode', 'literal')
    if mode == 'literal':
        args.append("--fixed-strings")
    elif mode == 'pcre2':
        args.append("--pcre2")

    case = options.get('case', 'auto')
    if case == 'sensitive':
        args.append("--case-sensitive")
    elif case == 'ignore':
        args.append("--ignore-case")
    else:
        args.append("--smart-case")

    if options.get('word'):
        args.append("--word-regexp")
    if options.get('whole_line'):
        args.append("--line-regexp")
    if options.get('multiline'):
        args.append("--multiline")

    context = options.get('context')
    if context:
        c = _parse_int(context, "context", 0, MAX_CONTEXT)
        args.extend(["-C", str(c)])

    max_count = options.get('max_count')
    if max_count:
        mc = _parse_int(max_count, "max_count", 1, MAX_COUNT)
        args.extend(["--max-count", str(mc)])

    encoding = options.get('encoding', 'auto')
    if encoding and encoding != 'auto':
        args.extend(["--encoding", encoding])

    # Scope logic: folder vs selected files
    if not scope_paths:
        # Folder scan: apply filters
        for e in _parse_extensions(options.get('extensions', '')):
            args.extend(["--glob", f"*.{e}"])
        for g in _parse_excludes(options.get('excludes', '')):
            args.extend(["--glob", f"!{g}"])
        if options.get('hidden'):
            args.append("--hidden")
        if options.get('ignored'):
            args.append("--no-ignore")
        depth = options.get('depth')
        if depth:
            d = _parse_int(depth, "depth", 1, MAX_DEPTH)
            args.extend(["--max-depth", str(d)])
        target = folder
    else:
        # Selected files: no re-application of traversal rules (native explicit args override)
        target = None

    args.append("--")
    args.append(options['pattern'])

    if target:
        args.append(target)
    else:
        args.extend(scope_paths)

    return args

def _parse_fd_output(stdout: bytes, stderr: bytes, rc: int) -> Dict[str, Any]:
    base = {"stdout": stdout, "stderr": stderr, "returncode": rc, "engine": "fd", "rows": [], "total": 0, "displayed_truncated": False}
    if rc != 0:
        return base

    try:
        text = stdout.decode('utf-8')
    except UnicodeDecodeError as e:
        raise ValueError(f"Invalid UTF-8 in fd output: {e}")

    paths = [p for p in text.split('\x00') if p]

    seen = set()
    unique_paths = []
    for p in paths:
        if not p or '\x00' in p:
            continue
        if p not in seen:
            seen.add(p)
            unique_paths.append(p)

    total = len(unique_paths)
    displayed = unique_paths[:MAX_DISPLAY]

    rows = [{"path": p} for p in displayed]
    base["rows"] = rows
    base["total"] = total
    base["displayed_truncated"] = total > MAX_DISPLAY
    return base

def _decode_rg_field(field: Any, is_path: bool = False) -> str:
    if not isinstance(field, dict):
        raise ValueError("Invalid ripgrep field type")
    if 'text' in field:
        val = field['text']
        if not isinstance(val, str):
            raise ValueError("Invalid text field type")
        if is_path:
            if '\x00' in val or not val:
                raise ValueError("Path must be non-empty and contain no NUL")
            return val.encode('utf-8').decode('utf-8')
        return val
    elif 'bytes' in field:
        raw_b64 = field['bytes']
        if not isinstance(raw_b64, str):
            raise ValueError("Invalid bytes field type")
        try:
            raw = base64.b64decode(raw_b64, validate=True)
        except Exception as e:
            raise ValueError(f"Invalid base64 in ripgrep output: {e}")
        if is_path:
            decoded = raw.decode('utf-8')
            if '\x00' in decoded or not decoded:
                raise ValueError("Path must be non-empty and contain no NUL")
            return decoded
        else:
            return raw.decode('utf-8', errors='replace')
    else:
        raise ValueError("Ripgrep field missing 'text' or 'bytes'")

def _parse_rg_output(stdout: bytes, stderr: bytes, rc: int) -> Dict[str, Any]:
    base = {"stdout": stdout, "stderr": stderr, "returncode": rc, "engine": "rg", "rows": [], "total": 0, "displayed_truncated": False}

    if rc not in (0, 1):
        return base

    rows: List[Dict[str, Any]] = []
    match_count = 0
    total_lines = 0

    for line in stdout.split(b'\n'):
        if not line.strip():
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError as e:
            raise ValueError(f"Malformed ripgrep JSON output: {e}")

        if not isinstance(obj, dict):
            raise ValueError("Ripgrep JSONL record must be an object")

        t = obj.get('type')
        if t in ('match','context') and not isinstance(obj.get('data'),dict):raise ValueError('検索結果の項目が不正です。')
        if t in ('begin', 'end', 'summary'):
            continue
        elif t == 'match':
            match_count += 1
            total_lines += 1
            data = obj.get('data', {})
            path_str = _decode_rg_field(data.get('path', {}), is_path=True)
            text_str = _decode_rg_field(data.get('lines', {}))
            line_num = data.get('line_number')
            if not isinstance(line_num, int) or isinstance(line_num, bool) or line_num < 1:
                raise ValueError("Invalid line_number in ripgrep match")
            row = {"kind": "match", "path": path_str, "line": line_num, "text": text_str}
            if len(rows) < MAX_DISPLAY:
                rows.append(row)
        elif t == 'context':
            total_lines += 1
            data = obj.get('data', {})
            path_str = _decode_rg_field(data.get('path', {}), is_path=True)
            text_str = _decode_rg_field(data.get('lines', {}))
            line_num = data.get('line_number')
            if not isinstance(line_num, int) or isinstance(line_num, bool) or line_num < 1:
                raise ValueError("Invalid line_number in ripgrep context")
            row = {"kind": "context", "path": path_str, "line": line_num, "text": text_str}
            if len(rows) < MAX_DISPLAY:
                rows.append(row)
        else:
            raise ValueError(f"Unknown ripgrep JSON event type: {t}")

    base["rows"] = rows
    base["total"] = match_count
    base["total_lines"] = total_lines
    base["displayed_truncated"] = total_lines > MAX_DISPLAY
    return base

def execute_job(exe: str, engine: str, options: dict, paths: list[str], cancel_event) -> dict:
    if engine not in ('fd', 'rg'):
        raise ValueError("Engine must be 'fd' or 'rg')")

    if engine=='fd' and paths:raise ValueError('名前検索には対象ファイルを指定できません。')
    folder = os.path.abspath(options['folder'])
    _validate_folder(folder)
    _validate_query(options['pattern'], engine)

    mode = options.get('pattern_mode', 'literal')
    case = options.get('case', 'auto')
    encoding = options.get('encoding', 'auto')

    if engine == 'fd':
        if mode not in ('literal', 'regex', 'glob'):
            raise ValueError("Invalid fd pattern_mode")
        if case not in ('auto', 'sensitive', 'ignore'):
            raise ValueError("Invalid fd case sensitivity")
    else:
        if mode not in ('literal', 'regex', 'pcre2'):
            raise ValueError("Invalid rg pattern_mode")
        if case not in ('auto', 'sensitive', 'ignore'):
            raise ValueError("Invalid rg case sensitivity")
        if encoding not in ('auto', 'utf-8', 'utf-16', 'shift_jis'):
            raise ValueError("Invalid rg encoding")

    args = []
    cwd = folder

    if engine == 'fd':
        args = _build_fd_args(options, folder)
    else:
        valid_paths = []
        seen = set()
        resolved_folder = Path(folder).resolve()

        for p in paths:
            abs_p = os.path.abspath(p)
            if abs_p in seen:
                continue
            seen.add(abs_p)

            if not os.path.isfile(abs_p):
                raise ValueError(f"Selected path is not a regular file: {abs_p}")
            if _is_link_or_ancestor_link(abs_p):
                raise ValueError(f"Symlinks or junctions rejected in selected files: {abs_p}")

            p_obj = Path(abs_p).resolve()
            if not p_obj.is_relative_to(resolved_folder):
                raise ValueError(f"Selected file outside folder scope: {abs_p}")

            valid_paths.append(abs_p)

        if len(valid_paths) > MAX_SCOPE:
            raise ValueError(f"Too many selected files (max {MAX_SCOPE})")

        args = _build_rg_args(options, valid_paths, folder)

    blocked_flags = []
    if engine == 'fd':
        blocked_flags = ["--exec", "--exec-batch", "-x", "-X"]
    elif engine == 'rg':
        blocked_flags = ["--pre", "--hostname-bin"]

    result = runtime.execute(
        exe=exe,
        args=args,
        stdin_data=b'',
        cwd=cwd,
        cancel_event=cancel_event,
        timeout=300,
        max_output=16 * 1024 * 1024,
        blocked_flags=blocked_flags
    )

    stdout = result.get('stdout', b'')
    stderr = result.get('stderr', b'')
    rc = result.get('returncode', -1)

    if engine == 'fd':
        return _parse_fd_output(stdout, stderr, rc)
    else:
        return _parse_rg_output(stdout, stderr, rc)
