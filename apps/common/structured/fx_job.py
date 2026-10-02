import runtime
from pathlib import Path

def execute_job(exe, mode, values, paths, text, cancel_event):
    if mode not in ('tree', 'query', 'version', 'help'):
        raise ValueError('不明なモードです。')
    if mode in ('help', 'version'):
        r = runtime.execute(exe, ['--' + mode], stdin_data=b'', cancel_event=cancel_event)
        r['extension'] = '.txt'
        return r
    args = []
    input_form = values.get('@input', 'json')
    if input_form not in ('json', 'yaml', 'toml', 'raw'):
        raise ValueError('入力形式が不正です。')
    if input_form == 'yaml':
        args.append('--yaml')
    elif input_form == 'toml':
        args.append('--toml')
    elif input_form == 'raw':
        args.append('--raw')
    if mode == 'query' and values.get('--slurp'):
        args.append('--slurp')
    if values.get('--strict'):
        args.append('--strict')
    if values.get('--no-inline'):
        args.append('--no-inline')
    stages = values.get('@stages', '.')
    if isinstance(stages, str):
        stages = [s.strip() for s in stages.splitlines() if s.strip()] or ['.']
    else:
        raise ValueError('式が不正です。')
    if mode == 'query':
        if len(stages) > 32:
            raise ValueError('式は最大32行までです。')
        for s in stages:
            if s.startswith('--comp'):
                raise ValueError('このオプションは使用できません。')
            native = {'--help', '-h', '--version', '-v', '-V', '--raw', '-r', '--slurp', '-s', '-rs', '-sr', '--yaml', '--toml', '--strict', '--no-inline', '--themes', '--export-themes', '--game-of-life'}
            if s in native:
                raise ValueError('ネイティブフラグを式として指定できません。')
        args.extend(stages)
    else:
        args.extend(['--slurp', '.'])
    stdin_data = b''
    if paths and text:
        raise ValueError('ファイルとテキストを同時に指定できません。')
    if paths:
        if len(paths) > 1:
            raise ValueError('ファイルは最大1つまでです。')
        p = Path(paths[0]).absolute()
        for part in [p, *p.parents]:
            if part.is_symlink() or part.is_junction():
                raise ValueError('シンボリックリンクまたはジャンクションは使用できません。')
        if not p.is_file():
            raise ValueError('ファイルが見つかりません。')
        if p.stat().st_size > 2 * 1024 * 1024:
            raise ValueError('ファイルサイズが2 MiBを超えています。')
        with p.open('rb') as fh:
            raw = fh.read(2 * 1024 * 1024 + 1)
        if len(raw) > 2 * 1024 * 1024:
            raise ValueError('ファイルサイズが2 MiBを超えています。')
        try:
            decoded = raw.decode('utf-8-sig', errors='strict')
        except UnicodeDecodeError:
            raise ValueError('UTF-8としてデコードできません。')
        if '\x00' in decoded:
            raise ValueError('NUL文字を含むファイルは使用できません。')
        stdin_data = decoded.encode('utf-8')
    elif text is not None and text != '':
        if len(text.encode('utf8')) > 2 * 1024 * 1024 or '\x00' in text:
            raise ValueError('テキストは最大2 MiBで、NUL文字を含めません。')
        stdin_data = text.encode('utf-8')
    result = runtime.execute(exe, args, stdin_data=stdin_data, cancel_event=cancel_event)
    ext = '.txt' if mode in ('help', 'version') else '.json'
    result['extension'] = ext
    return result
