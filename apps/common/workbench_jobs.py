"""Batch workers for bundled command-line tools; no scripts are executed."""
import runtime
import io
import os
import re
import tempfile
import threading
import time
import zipfile
from pathlib import Path
_MAX_INPUT_FILES = 2000
_MAX_INPUT_BYTES = 64 * 1024 * 1024
_MAX_OUTPUT_BYTES = 64 * 1024 * 1024
_MAX_ZIP_BYTES = 16 * 1024 * 1024
_MAX_REPORT_BYTES = 16 * 1024 * 1024
_BATCH_DEADLINE_S = 300
_SHELL_BLOCKED = ['-w', '--write', '-d', '--diff', '-l', '--list', '--to-json', '--from-json', '-f', '--find']

def _is_symlink_or_junction(path):
    return path.is_symlink() or path.is_junction()

def _walk_tree(root: Path, max_files=_MAX_INPUT_FILES, max_bytes=_MAX_INPUT_BYTES):
    if _is_symlink_or_junction(root):raise ValueError('リンクを含む入力は扱えません。')
    if root.is_file():
        size=root.stat().st_size
        if size>max_bytes:raise ValueError('入力サイズが上限を超えました。')
        return 1,size
    count = 0
    total = 0
    directory_count=0
    started=time.monotonic()
    def walk_error(error):raise error
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False,onerror=walk_error):
        directory_count+=1
        if directory_count>2000 or time.monotonic()-started>300:
            raise ValueError('フォルダー数または走査時間が上限を超えました。')
        pruned = []
        for d in dirnames:
            p = Path(dirpath) / d
            if _is_symlink_or_junction(p):
                raise ValueError(f'シンボリックリンク/ジャンクションを検出: {p}')
            pruned.append(d)
        dirnames[:] = pruned
        for fn in filenames:
            fp = Path(dirpath) / fn
            if _is_symlink_or_junction(fp):
                raise ValueError(f'シンボリックリンク/ジャンクションを検出: {fp}')
            count += 1
            try:
                total += fp.stat().st_size
            except OSError as error:
                raise ValueError('入力ファイルを読み取れません。') from error
            if count > max_files:
                raise ValueError(f'ファイル数が上限({_MAX_INPUT_FILES})を超えました。')
            if total > max_bytes:
                raise ValueError(f'合計サイズが上限(64 MiB)を超えました。')
    return (count, total)

def _extract_positional_paths(args: list[str]) -> list[str]:
    try:
        idx = args.index('--')
    except ValueError:
        return []
    return [a for a in args[idx + 1:] if not a.startswith('-')]

def _flags_before_delimiter(args: list[str]) -> list[str]:
    try:
        idx = args.index('--')
    except ValueError:
        return list(args)
    return list(args[:idx])

def _monitor_dir_size(folder: Path, stop_event: threading.Event, cancel_event: threading.Event):

    def _run():
        while not stop_event.is_set():
            total = 0
            try:
                for dp, dn, fn in os.walk(folder):
                    for f in fn:
                        fp = Path(dp) / f
                        try:
                            total += fp.stat().st_size
                        except OSError:
                            pass
                    if total > _MAX_OUTPUT_BYTES:
                        cancel_event.set()
                        return
            except Exception:
                break
            time.sleep(0.1)
    t = threading.Thread(target=_run, daemon=True)
    t.start()
    return t

def _make_zip_bytes(entries: list[tuple[str, bytes]]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
        for entry in entries:
            name,data=entry[:2]
            safe = Path(name).as_posix()
            if Path(safe).is_absolute() or ':' in safe or '..' in Path(safe).parts:
                raise ValueError(f'不正なZIPエントリ名: {name}')
            info=zipfile.ZipInfo(safe)
            info.compress_type=zipfile.ZIP_DEFLATED
            if len(entry)>2:
                metadata=entry[2]
                date=time.localtime(metadata.st_mtime)[:6]
                info.date_time=date if 1980<=date[0]<=2107 else (1980,1,1,0,0,0)
                info.external_attr=(metadata.st_mode & 0xffff)<<16
            zf.writestr(info, data)
    return buf.getvalue()

def _job_scc_report(exe: str, args: list[str], stdin_data: bytes, cancel_event: threading.Event | None, mode: dict) -> dict:
    runtime.build_command(exe, args, mandatory_args=(), blocked_flags=mode['_profile']['blocked_flags'])
    scan_paths = _extract_positional_paths(args)
    if not scan_paths:
        raise ValueError('スキャン対象パスが指定されていません。')
    first = Path(scan_paths[0])
    if first.is_dir():
        cwd = str(first)
    else:
        cwd = str(first.parent)
    pre_flags = _flags_before_delimiter(args)
    with tempfile.TemporaryDirectory(prefix='kiwi-scc-report-') as tmpdir:
        report_path = Path(tmpdir) / 'report.html'
        internal_args = ['--no-config', f'--report={report_path}'] + pre_flags + ['--'] + scan_paths
        result = runtime.execute(exe, internal_args, stdin_data=stdin_data, cwd=cwd, cancel_event=cancel_event, timeout=_BATCH_DEADLINE_S, mandatory_args=(), blocked_flags=[f for f in mode['_profile']['blocked_flags'] if f != '--report'])
        if result['returncode'] != 0:
            raise ValueError(f"scc レポート生成に失敗しました (rc={result['returncode']})")
        if not report_path.is_file():
            raise ValueError('レポートファイルが生成されませんでした。')
        size = report_path.stat().st_size
        if size > _MAX_REPORT_BYTES:
            raise ValueError('レポートサイズが上限(16 MiB)を超えました。')
        html_bytes = report_path.read_bytes()
    return {'stdout': html_bytes, 'display': 'HTMLレポートを作成しました。結果を保存してください。', 'extension': '.html', 'returncode': 0}

def _job_minify_zip(exe: str, args: list[str], stdin_data: bytes, cancel_event: threading.Event | None, mode: dict) -> dict:
    runtime.build_command(exe, args, mandatory_args=(), blocked_flags=mode['_profile']['blocked_flags'])
    input_paths = _extract_positional_paths(args)
    if not input_paths:
        raise ValueError('入力パスが指定されていません。')
    pre_flags = _flags_before_delimiter(args)
    for i, a in enumerate(pre_flags):
        if a == '--preserve' or a.startswith('--preserve='):
            val = a.split('=', 1)[1] if '=' in a else pre_flags[i + 1] if i + 1 < len(pre_flags) else ''
            tokens = set(val.replace(',', ' ').replace('[', ' ').replace(']', ' ').split())
            if tokens & {'links', 'all', 'ownership'}:
                raise ValueError('--preserve links/all はWindowsでサポートされません。')
    total_files = 0
    total_bytes = 0
    for p in input_paths:
        pp = Path(p)
        if not pp.exists():
            raise ValueError(f'入力パスが存在しません: {p}')
        if _is_symlink_or_junction(pp):
            raise ValueError(f'シンボリックリンク/ジャンクションを検出: {p}')
        if pp.is_dir():
            cnt, size = _walk_tree(pp)
            total_files += cnt
            total_bytes += size
        else:
            total_files += 1
            total_bytes += pp.stat().st_size
    if total_bytes > _MAX_INPUT_BYTES:
        raise ValueError('入力合計サイズは64 MiBまでです。')
    if total_files > _MAX_INPUT_FILES:
        raise ValueError(f'入力ファイル数が上限({_MAX_INPUT_FILES})を超えました。')
    basenames = [Path(p).name.casefold() for p in input_paths]
    if len(basenames) != len(set(basenames)):
        raise ValueError('トップレベルのベース名が重複しています。')
    pre_flags = _flags_before_delimiter(args)
    with tempfile.TemporaryDirectory(prefix='kiwi-minify-out-') as tmpdir:
        out_dir = Path(tmpdir) / 'out'
        out_dir.mkdir()
        internal_args = pre_flags + [f'--output={out_dir}/', '--'] + input_paths
        stop_evt = threading.Event()
        mon_thread = _monitor_dir_size(out_dir, stop_evt, cancel_event)
        try:
            result = runtime.execute(exe, internal_args, stdin_data=stdin_data, cancel_event=cancel_event, timeout=_BATCH_DEADLINE_S, mandatory_args=(), blocked_flags=[f for f in mode['_profile']['blocked_flags'] if f not in ('--output', '-o')])
        finally:
            stop_evt.set()
            mon_thread.join(timeout=2)
        if result['returncode'] != 0:
            raise ValueError(f"minify 実行に失敗しました (rc={result['returncode']})")
        if cancel_event and cancel_event.is_set():
            raise InterruptedError('処理を停止しました。')
        out_files = []
        for dp, dn, fn in os.walk(out_dir):
            for f in fn:
                fp = Path(dp) / f
                if _is_symlink_or_junction(fp):
                    raise ValueError(f'出力にシンボリックリンク/ジャンクションを検出: {fp}')
                out_files.append(fp)
        if not out_files:
            raise ValueError('出力ファイルがありません。条件を確認してください。')
        if len(out_files) > _MAX_INPUT_FILES:
            raise ValueError('出力ファイル数が上限を超えました。')
        total_out = sum((f.stat().st_size for f in out_files))
        if total_out > _MAX_OUTPUT_BYTES:
            raise ValueError('出力合計サイズが上限(64 MiB)を超えました。')
        entries = []
        for fp in sorted(out_files):
            rel = fp.relative_to(out_dir).as_posix()
            data = fp.read_bytes()
            entries.append((rel, data,fp.stat()))
        if not entries:
            raise ValueError('出力ファイルが空です。')
        zip_bytes = _make_zip_bytes(entries)
        if len(zip_bytes) > _MAX_ZIP_BYTES:
            raise ValueError('ZIPサイズが上限(16 MiB)を超えました。')
    n_files = len(out_files)
    return {'stdout': zip_bytes, 'display': f'一括処理完了: {n_files}ファイル。結果をZIPとして保存してください。', 'extension': '.zip', 'returncode': 0}

def execute_job(profile, exe, args, stdin_data=b'', cancel_event=None, mode=None):
    if not isinstance(profile, dict) or 'slug' not in profile:
        raise ValueError('profile must be a dict with slug')
    mode = dict(mode or {})
    cancel_event = cancel_event or threading.Event()
    mode['_profile'] = profile
    blocked = list(profile.get('blocked_flags', []))
    mandatory = tuple(profile.get('mandatory_args', []))
    job_type = mode.get('job', '')
    if job_type == 'report':
        result = _job_scc_report(exe, args, stdin_data, cancel_event, mode)
        result.setdefault('stderr', b'')
        return result
    elif job_type == 'minify_zip':
        result = _job_minify_zip(exe, args, stdin_data, cancel_event, mode)
        result.setdefault('stderr', b'')
        return result
    elif job_type == 'shell_zip':
        return _job_shell_zip(exe, args, stdin_data, cancel_event, mode)
    else:
        runtime.build_command(exe, args, mandatory_args=mandatory, blocked_flags=blocked)
        targets = _extract_positional_paths(args)
        cwd = None
        if profile['slug'] == 'kiwi-count' and targets:
            first = Path(targets[0])
            cwd = str(first if first.is_dir() else first.parent)
        result = runtime.execute(exe, args, stdin_data=stdin_data, cwd=cwd, cancel_event=cancel_event, timeout=_BATCH_DEADLINE_S, mandatory_args=mandatory, blocked_flags=blocked)
        return result

def _job_shell_zip(exe, args, stdin_data, cancel_event, mode):
    profile = mode['_profile']
    blocked = list(profile.get('blocked_flags', [])) + _SHELL_BLOCKED
    mandatory = tuple(profile.get('mandatory_args', []))
    runtime.build_command(exe, args, mandatory_args=mandatory, blocked_flags=blocked)
    pre_flags = _flags_before_delimiter(args)
    input_paths = _extract_positional_paths(args)
    if not input_paths:
        raise ValueError('入力パスが指定されていません。')
    deadline = time.monotonic() + _BATCH_DEADLINE_S
    total_files, total_bytes = (0, 0)
    for p in input_paths:
        pp = Path(p)
        if not pp.exists():
            raise ValueError(f'入力パスが存在しません: {p}')
        if _is_symlink_or_junction(pp):
            raise ValueError(f'シンボリックリンク/ジャンクションを検出: {p}')
        cnt, bts = _walk_tree(pp)
        total_files += cnt
        total_bytes += bts
    if total_files > _MAX_INPUT_FILES or total_bytes > _MAX_INPUT_BYTES:
        raise ValueError('入力ファイル数またはサイズが上限を超えました。')
    detect_val = 'default'
    apply_ignore = False
    for i, a in enumerate(pre_flags):
        if a == '--detect':
            detect_val = pre_flags[i + 1] if i + 1 < len(pre_flags) else 'default'
        elif a.startswith('--detect='):
            detect_val = a.split('=', 1)[1]
        elif a == '--apply-ignore':
            apply_ignore = True
    find_args = ['--find=0', '--detect', detect_val]
    if apply_ignore:
        find_args.append('--apply-ignore')
    find_args += ['--'] + input_paths
    result_find = runtime.execute(exe, find_args, stdin_data=b'', cancel_event=cancel_event, timeout=max(0.1, deadline - time.monotonic()), mandatory_args=mandatory, blocked_flags=[])
    if result_find['returncode'] != 0:
        raise ValueError(f"shfmt --find に失敗しました (rc={result_find['returncode']})")
    nul_paths = [p for p in result_find['stdout'].split(b'\x00') if p]
    script_paths = []
    for np_ in nul_paths:
        sp = os.fsdecode(np_)
        pp = Path(sp)
        if _is_symlink_or_junction(pp):
            raise ValueError(f'シンボリックリンク/ジャンクションを検出: {sp}')
        script_paths.append(pp)
    if not script_paths:
        raise ValueError('シェルスクリプトが見つかりませんでした。')
    if len(script_paths) > _MAX_INPUT_FILES:
        raise ValueError('ファイル数が上限を超えました。')
    single_root = None
    if len(input_paths) == 1 and Path(input_paths[0]).is_dir():
        single_root = Path(input_paths[0])
    entries = []
    total_out = 0
    for idx, sp in enumerate(script_paths):
        if cancel_event and cancel_event.is_set():
            raise InterruptedError('処理を停止しました。')
        if time.monotonic() > deadline:
            raise TimeoutError('時間制限に達したため停止しました。')
        if single_root:
            rel = sp.relative_to(single_root).as_posix()
        else:
            found = None
            for root_index, target in enumerate(input_paths):
                source = Path(target)
                parent = source if source.is_dir() else source.parent
                if source.is_dir() and sp.is_relative_to(source) or sp == source:
                    found = (root_index, parent)
                    break
            if found is None:
                raise ValueError('選択した入力以外のファイルを検出しました。')
            rel = f'input{found[0]}/' + sp.relative_to(found[1]).as_posix()
        fmt_args = pre_flags + ['--', str(sp)]
        result_fmt = runtime.execute(exe, fmt_args, stdin_data=b'', cancel_event=cancel_event, timeout=max(0.1, deadline - time.monotonic()), mandatory_args=mandatory, blocked_flags=[])
        if result_fmt['returncode'] != 0:
            raise ValueError(result_fmt['stderr'].decode('utf8', 'replace'))
        data = result_fmt['stdout']
        total_out += len(data)
        if total_out > _MAX_OUTPUT_BYTES:
            raise ValueError('出力合計サイズが上限(64 MiB)を超えました。')
        entries.append((rel, data))
    if cancel_event and cancel_event.is_set():
        raise InterruptedError('処理を停止しました。')
    zip_bytes = _make_zip_bytes(entries)
    if len(zip_bytes) > _MAX_ZIP_BYTES:
        raise ValueError('ZIPサイズが上限(16 MiB)を超えました。')
    return {'stdout': zip_bytes, 'stderr': b'', 'display': f'シェルスクリプト {len(script_paths)} 件を整形してZIPにしました。', 'extension': '.zip', 'returncode': 0}
