"""Adapters for the original native workers and the shared document context."""
from pathlib import Path
import runtime,workbench,workbench_jobs,inputs
validate_path=inputs.validate_path

def execute(engine,exe,profile,mode,values,paths,text,cancel_event):
    paths,text=inputs.validate_inputs(engine,mode,paths,text)
    info=not mode.get('files') and not mode.get('stdin')
    if engine=='code2prompt':
        return inputs.run_prompt(exe,profile,mode,values,paths,cancel_event)
    args=workbench.build_args(profile,values,mode['label'],paths) if engine!='bat' else list(mode.get('args',[]))
    stdin=text.encode('utf8')
    if engine=='bat':
        if not info:
            try:first=int(values.get('@first','1'));tabs=int(values.get('--tabs','4'))
            except (ValueError,TypeError):raise ValueError('開始行とタブ幅は整数で指定してください。') from None
            theme=values.get('--theme','TwoDark')
            if not 1<=first<=999999999 or not 1<=tabs<=32:raise ValueError('開始行は1〜999999999、タブ幅は1〜32です。')
            if theme not in ('TwoDark','GitHub','Dracula'):raise ValueError('テーマの指定が正しくありません。')
            args=['--color=always','--decorations=always','--style=numbers','--wrap=never','--theme',theme,'--line-range',f'{first}:{first+499}','--tabs',str(tabs)]
            if values.get('--language'):args+=['--language',values['--language']]
            if values.get('--show-all'):args.append('--show-all')
            args+=['--',paths[0]] if paths else ['--file-name','input.txt']
        result=runtime.execute(exe,args,stdin_data=None if paths else stdin,cancel_event=cancel_event,timeout=15,max_output=2*1024*1024,mandatory_args=['--paging=never'],blocked_flags=['--pager','--config-file'])
        result['extension']='.txt' if info else '.ansi.txt'
    elif engine in ('glow','shfmt'):
        if engine=='glow':
            if mode.get('url'):
                url=text.strip()
                if not url or any(c.isspace() for c in url) or not url.startswith(('https://','http://','github://','gitlab://','github.com/','gitlab.com/')):raise ValueError('許可されたURLまたはリポジトリを指定してください。')
                args+=['--',url];stdin=None
            elif paths:stdin=None
        result=workbench_jobs.execute_job(profile,exe,args,stdin,cancel_event,mode)
        if engine=='glow':result['extension']='.ansi.txt'
        else:result.setdefault('extension',{'整形':'.sh','AST JSONから整形':'.sh','AST JSONへ':'.json','差分':'.diff'}.get(mode['label'],'.txt'))
    else:raise ValueError('未対応の用途です。')
    result.update(engine=engine,mode_label=mode['label'],transferable_type=None)
    if engine=='shfmt' and result['returncode']==0 and mode['label'] in ('整形','AST JSONから整形') and (not paths or len(paths)==1 and Path(paths[0]).is_file()):result['transferable_type']='shell'
    return result
