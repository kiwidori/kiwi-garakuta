"""Verify real native workflows of the three Go-backed wrappers on Windows."""
from __future__ import annotations
import argparse
import ctypes
import hashlib
import io
import json
from pathlib import Path
import sys
import threading
import time
import zipfile

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'apps/common'))
from runtime import execute
from workbench import App, build_args
from three_fixtures import prepare, PUBLIC, TEXTS


def context(slug):
    from prepare_three_tools import prepare
    source=ROOT/'apps'/slug
    profile=json.loads((source/'profile.json').read_text(encoding='utf8'))
    values={f['flag']: f['default'] for f in profile['fields']}
    return source,profile,values,prepare(slug)


def cli():
    from workbench_jobs import execute_job
    code,shell,web=prepare()
    snapshots={p:hashlib.sha256(p.read_bytes()).hexdigest() for folder in (code,shell,web) for p in folder.rglob('*') if p.is_file()}
    checks=[]
    def run(slug,label,paths=(),data=b'',changes=None):
        _,p,v,exe=context(slug); v.update(changes or {})
        mode=next(m for m in p['modes'] if m['label']==label)
        args=build_args(p,v,label,list(paths))
        r=execute_job(p,exe,args,data,threading.Event(),mode)
        assert r['returncode'] in mode.get('success_codes',[0]),(slug,label,r['stderr'][:400])
        checks.append(slug+': '+label)
        return r['stdout']
    rows=json.loads(run('kiwi-count','コード集計',[code],changes={'--format':'json','--by-file':True,'--uloc':True,'--cognitive':True}))
    assert {r['Name'] for r in rows}>={'Python','JavaScript'} and any(r['Files'] for r in rows)
    rows=json.loads(run('kiwi-count','コード集計',[code],changes={'--format':'json','--include-ext':'py'}))
    assert [r['Name'] for r in rows]==['Python']
    for fmt in ('csv','html','sql','openmetrics'):
        assert run('kiwi-count','コード集計',[code],changes={'--format':fmt})
    for flag in ('--hotspots','--coupling','--by-author','--timeline'):
        assert run('kiwi-count','コード集計',[code],changes={flag:True})
    assert run('kiwi-count','コード集計',[code],changes={'--locomo':True,'--cost-comparison':True,'--locomo-preset':'local'})
    assert b'<html' in run('kiwi-count','HTMLレポート',[code],changes={'--report-title':'Demo report'}).lower()
    script=(shell/'hello.sh').read_bytes()
    formatted=run('kiwi-shell','整形',data=script,changes={'--indent':'2','--language-dialect':'bash'})
    assert b'  echo' in formatted
    assert run('kiwi-shell','差分',[shell/'hello.sh'])
    assert b'hello.sh' in run('kiwi-shell','変更が必要なファイル一覧',[shell/'hello.sh'])
    assert b'hello.sh' in run('kiwi-shell','スクリプト検出',[shell])
    ast=run('kiwi-shell','AST JSONへ',data=script); assert json.loads(ast)['Type']=='File'
    assert b'echo' in run('kiwi-shell','AST JSONから整形',data=ast)
    assert len(run('kiwi-shell','整形',data=script,changes={'--minify':True}))<len(script)
    z=zipfile.ZipFile(io.BytesIO(run('kiwi-shell','フォルダー整形ZIP',[shell],changes={'--indent':'2'})))
    assert any(n.endswith('hello.sh') and b'  echo' in z.read(n) for n in z.namelist())
    for fmt,text in TEXTS.items():
        output=run('kiwi-minify','圧縮',data=text.encode(),changes={'--type':fmt})
        assert output and len(output)<=len(text.encode())
    kept=run('kiwi-minify','圧縮',data=TEXTS['html'].encode(),changes={'--type':'html','--html-keep-comments':True})
    assert b'<!--demo-->' in kept
    bundle=run('kiwi-minify','圧縮',[web/'demo.css',web/'nested/more.css'],changes={'--bundle':True})
    assert b'body{' in bundle and b'p{' in bundle
    zipped=run('kiwi-minify','フォルダー圧縮ZIP',[web],changes={'--recursive':True,'--sync':True,'--preserve':'mode,timestamps'})
    z=zipfile.ZipFile(io.BytesIO(zipped));assert any(n.endswith('notes.txt') for n in z.namelist())
    assert any(n.endswith('nested/more.css') for n in z.namelist())
    for slug in ('kiwi-count','kiwi-shell','kiwi-minify'):
        _,p,v,exe=context(slug)
        assert run(slug,'バージョン')
        # Every dedicated widget feeds the argument builder; verify binding coverage without executing conflicting flags together.
        for field in p['fields']:
            changed=dict(v);changed[field['flag']]=True if field['type']=='bool' else (next((c for c in field.get('choices',[]) if c),'demo'))
            args=build_args(p,changed,p['modes'][0]['label'],[code] if slug=='kiwi-count' else [])
            assert field['flag'] in args,field['flag']
        try: execute(exe,['--output','unwanted'] if slug!='kiwi-shell' else ['--write'],blocked_flags=p['blocked_flags'])
        except ValueError:pass
        else:raise AssertionError('blocked write accepted')
    assert all(hashlib.sha256(p.read_bytes()).hexdigest()==sha for p,sha in snapshots.items()),'source changed'
    result=ROOT/'data/batch3/windows-results.json';result.write_text(json.dumps(checks,ensure_ascii=False,indent=2),encoding='utf8')
    print('PASS:',len(checks),'real CLI workflows, native argument binding, blocked writes, unchanged inputs')


def gui():
    from PIL import ImageGrab
    ctypes.windll.user32.SetProcessDPIAware()
    code,shell,web=prepare()
    for slug in ('kiwi-count','kiwi-shell','kiwi-minify'):
        source,p,_,exe=context(slug);app=App(p,source)
        app.exe_path=str(exe);app.root.geometry('1100x850+40+30')
        if slug=='kiwi-count':app.paths=[str(code)];app.path_list.insert('end',str(code));app.values['--by-file'].set(True)
        else:
            app.in_text.insert('1.0',(shell/'hello.sh').read_text(encoding='utf8') if slug=='kiwi-shell' else TEXTS['html'])
            if slug=='kiwi-minify':app.values['--type'].set('html')
        app.root.update();app.run()
        deadline=time.monotonic()+30
        while app.worker and app.worker.is_alive() and time.monotonic()<deadline:
            app.root.update();time.sleep(.03)
        for _ in range(5):app.root.update();time.sleep(.1)
        assert app.last_result and app.last_result['returncode']==0,app.last_result
        assert app.out_text.get('1.0','end').strip()
        assert len(app.tabs.tabs())==len({f['group'] for f in p['fields']})
        app.root.lift();app.root.update();time.sleep(.3)
        x,y=app.root.winfo_rootx(),app.root.winfo_rooty()
        ImageGrab.grab(bbox=(x,y,x+app.root.winfo_width(),y+app.root.winfo_height())).save(ROOT/'site/assets/screenshots'/f'{slug}-public.png')
        app.advanced.exe_path=str(exe);app.advanced.open_window();app.root.update()
        assert len(app.advanced.option_tree.get_children())==len(app.advanced.spec['options'])
        app.advanced._on_toplevel_close();app.root.update();app._on_close()
        print('PASS:',slug,'native GUI workflow, settings tabs, advanced window, screenshot, close')


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('stage',choices=['cli','gui']);args=parser.parse_args()
    globals()[args.stage]()
