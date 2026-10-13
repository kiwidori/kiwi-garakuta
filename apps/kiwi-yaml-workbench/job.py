"""Shared YAML jobs; source files remain unchanged."""
import tempfile,time
from pathlib import Path
import runtime,yamlfmt_job,check_job
from format_view import parse_settings

def yq_job(exe,mode,values,paths,text,cancel):
    if mode in ('help','version'):
        r=runtime.execute(exe,['--'+mode],cancel_event=cancel,timeout=15,max_output=4*1024*1024);r['extension']='.txt';return r
    if text and paths:raise ValueError('テキストとファイルは同時に指定できません。')
    if not text.strip() and not paths:raise ValueError('データを入力するかファイルを指定してください。')
    if len(text.encode('utf8'))>2*1024*1024:raise ValueError('テキストは2 MiBまでです。')
    if len(paths)>200:raise ValueError('yqの対象は200ファイルまでです。')
    if mode not in ('yaml','json','query','all'):raise ValueError('用途を選択してください。')
    expression='.' if mode in ('yaml','json') else values.get('@expression','.')
    if not isinstance(expression,str) or not expression or '\x00' in expression or len(expression.encode('utf8'))>16*1024:raise ValueError('式はNULを含まない16 KiBまでの文字列で指定してください。')
    input_format=values.get('@input','yaml');output_format=mode if mode in ('yaml','json') else values.get('@output','yaml')
    if input_format not in ('yaml','json') or output_format not in ('yaml','json'):raise ValueError('YAMLまたはJSONの形式を選択してください。')
    deadline=time.monotonic()+15
    with tempfile.TemporaryDirectory(prefix='kiwi-yaml-workbench-') as td:
        folder=Path(td);staged=[];total=0
        for i,value in enumerate(paths):
            yamlfmt_job.check(cancel,deadline);p=yamlfmt_job.safe_path(value)
            if not p.is_file():raise ValueError('yqの対象にはファイルを指定してください。')
            with p.open('rb') as f:raw=f.read(2*1024*1024+1)
            if len(raw)>2*1024*1024:raise ValueError('yqの入力は1ファイル2 MiBまでです。')
            total+=len(raw)
            if total>64*1024*1024:raise ValueError('ファイルは合計64 MiBまでです。')
            raw.decode('utf-8-sig');destination=folder/f'{i:04d}.yaml';destination.write_bytes(raw);staged.append(str(destination))
        args=['eval-all' if mode=='all' else 'eval','--input-format='+input_format,'--output-format='+output_format,'--no-colors','--security-disable-env-ops','--security-disable-file-ops']
        if output_format=='yaml':args.append('--prettyPrint')
        args+=['--',expression,*staged] if staged else ['--',expression,'-']
        r=runtime.execute(exe,args,stdin_data=None if staged else text.encode('utf8'),cwd=td,cancel_event=cancel,timeout=max(.1,deadline-time.monotonic()),max_output=4*1024*1024)
        r['extension']='.'+output_format;return r

def execute(engine,exe,mode,values,paths,text,config,profile,cancel):
    if len(text.encode('utf8'))>2*1024*1024:raise ValueError('入力テキストは2 MiBまでです。')
    if engine=='yq':r=yq_job(exe,mode,values,paths,text,cancel)
    elif engine=='yamlfmt':
        if mode in ('format','dry','lint') and text.strip() and paths:raise ValueError('テキストとファイルは同時に指定できません。')
        args,conf=parse_settings(config,values,profile)
        r=yamlfmt_job.execute_job(exe,args,text.encode('utf8'),cancel,mode,paths,conf,values.get('@patterns',''))
    elif engine=='actionlint':
        if mode in ('lint','json','custom'):
            for p in paths:yamlfmt_job.safe_path(p)
        r=check_job.execute_job(exe,mode,values,paths,text,cancel)
    else:raise ValueError('用途を選択してください。')
    r.update(engine=engine,mode=mode,transferable=engine=='yq' and mode in ('yaml','json','query','all') or engine=='yamlfmt' and mode=='format' and r.get('extension')=='.yaml')
    return r
