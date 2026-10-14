from pathlib import Path
import workbench
import prompt_backend

def validate_path(path):
    p = Path(path).absolute()
    if not p.exists():
        raise ValueError("パスが存在しません")
    for part in [p, *p.parents]:
        try:
            if part.is_symlink() or part.is_junction():
                raise ValueError("シンボリックリンクまたはJUNCTIONは許可されていません")
        except OSError as e:
            raise ValueError(f"パス検証エラー: {e}") from e
    return str(p)

def validate_inputs(engine, mode, paths, text):
    if not mode.get('files', False) and not mode.get('stdin', False):
        return [], ''
    if engine == 'code2prompt':
        if not mode.get('files', False) or len(paths) != 1:
            raise ValueError("code2promptはフォルダ1つが必要です")
        p = validate_path(paths[0])
        if not Path(p).is_dir():
            raise ValueError("ディレクトリを指定してください")
        return [p], ''
    if paths and text.strip():
        raise ValueError("パスとテキストの同時指定はできません")
    if paths:
        if not mode.get('files', False):
            raise ValueError("ファイル入力モードではありません")
        if engine in ("bat", "glow") and len(paths) != 1:
            raise ValueError("閲覧するファイルは1つ指定してください。")
        validated = []
        for path in paths:
            p = validate_path(path)
            pp = Path(p)
            if pp.is_dir():
                if not mode.get('allow_dirs', True):
                    raise ValueError("ディレクトリ指定は許可されていません")
            else:
                if engine == 'bat' and pp.stat().st_size > 10 * 1024 * 1024:
                    raise ValueError("batファイルサイズ超過(10MiB)")
                elif engine == 'glow' and pp.stat().st_size > 2 * 1024 * 1024:
                    raise ValueError("glowファイルサイズ超過(2MiB)")
            validated.append(p)
        return validated, ''
    if not mode.get('stdin', False):
        raise ValueError("テキスト入力モードではありません")
    if not isinstance(text, str) or not text.strip():
        raise ValueError("テキストが空です")
    if '\x00' in text or len(text.encode('utf-8')) > 2 * 1024 * 1024:
        raise ValueError("テキスト形式エラー(NULまたは2MiB超過)")
    return [], text

def run_prompt(exe, profile, mode, values, paths, cancel_event):
    args = workbench.build_args(profile, values, mode['label'], paths)
    result = prompt_backend.process(exe, args, b'', mode, cancel_event)
    result['engine'] = 'code2prompt'
    result['mode_label'] = mode['label']
    if result.get('returncode') == 0 and mode.get('files', False) and result.get('extension') == '.md':
        result['transferable_type'] = 'markdown'
    else:
        result['transferable_type'] = None
    return result
