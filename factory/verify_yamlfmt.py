"""Windows checks for formatting options, source preservation and portable launch."""
import sys,json,time,threading,io,zipfile,hashlib,tempfile,importlib.util,ctypes,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];APP=ROOT/'apps/kiwi-yamlfmt'
sys.path.insert(0,str(APP));sys.path.insert(0,str(ROOT/'apps/common'))
EXE=ROOT/'.tools/kiwi-yamlfmt/yamlfmt.exe'
PROFILE=json.loads((APP/'profile.json').read_text(encoding='utf8'))
def load():
    spec=importlib.util.spec_from_file_location('kiwi_yamlfmt',APP/'main.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
def cli():
    from yamlfmt_job import execute_job
    m=load();count=0
    def run(mode='format',data=b'app:\n name: kiwi\n list: [a,b]\n',paths=(),values=None,config='{}',patterns=''):
        nonlocal count
        args,config=m.parse_settings(config,values or {},PROFILE)
        r=execute_job(str(EXE),args,data,threading.Event(),mode,list(paths),config,patterns)
        count+=1;return r
    r=run();assert r['returncode']==0 and b'  name: kiwi' in r['stdout']
    assert b'    name: kiwi' in run(values={'@f.indent':'4'})['stdout']
    assert b'\r\n' not in run(values={'@line_ending':'lf'})['stdout']
    assert b'\r\n' in run(values={'@line_ending':'crlf'})['stdout']
    assert run(values={'@f.include_document_start':'true'})['stdout'].startswith(b'---')
    assert b'[' in run(values={'@f.force_array_style':'flow'})['stdout']
    assert b'- a' in run(values={'@f.force_array_style':'block'})['stdout']
    assert b'"hello"' in run(data=b"title: 'hello'\n",values={'@f.force_quote_style':'double'})['stdout']
    assert b"'hello'" in run(data=b'title: "hello"\n',values={'@f.force_quote_style':'single'})['stdout']
    assert run(data=b'a: &anchor 1\nb: *anchor\n',values={'@f.disallow_anchors':'true'})['returncode']!=0
    for f in PROFILE['fields']:
        if f['flag'].startswith('@f.'):
            value='4' if f['type']=='text' else f['choices'][0]
            r=run(values={f['flag']:value});assert r['returncode']==0,(f,r)
    ky=run(values={'@formatter':'kyaml'});assert ky['returncode']==0 and b'{' in ky['stdout']
    try:m.parse_settings('{}',{'@formatter':'kyaml','@f.indent':'4'},PROFILE)
    except ValueError:pass
    else:raise AssertionError('Incompatible KYAML options accepted')
    assert run(mode='config',data=b'')['stdout']
    assert b'0.21.0' in run(mode='version',data=b'')['stdout']
    assert b'yamlfmt' in run(mode='help',data=b'')['stdout']
    assert run(mode='dry')['returncode']==0
    lint=run(mode='lint');assert lint['returncode']==1 and lint.get('status')=='differences' and b'formatting differences' in lint['stdout']
    bad=run(mode='lint',data=b'broken: [');assert bad['returncode']!=0 and bad.get('status')!='differences'
    assert run(data=b'broken: [')['returncode']!=0
    with tempfile.TemporaryDirectory(prefix='kiwi-yamlfmt-test-') as td:
        p=Path(td);folder=p/'日本語 フォルダー';folder.mkdir()
        (folder/'nested').mkdir();(folder/'demo.yaml').write_bytes(b'app:\n name: kiwi\n')
        (folder/'nested/other.yml').write_bytes(b'nested:\n x: 1\n');(folder/'note.txt').write_bytes(b'not YAML')
        (folder/'.gitignore').write_text('nested/\n',encoding='utf8')
        (folder/'yamlfmt.patterns').write_text('*.yaml\n*.yml\n!nested/\n',encoding='utf8')
        (folder/'custom.tpl').write_bytes(b'custom:\n x: 1\n')
        snapshot={f:hashlib.sha256(f.read_bytes()).hexdigest() for f in folder.rglob('*') if f.is_file()}
        r=run(data=b'',paths=[folder]);assert r['returncode']==0
        z=zipfile.ZipFile(io.BytesIO(r['stdout']));assert any(n.endswith('demo.yaml') and b'  name' in z.read(n) for n in z.namelist())
        assert not any(n.endswith('note.txt') for n in z.namelist())
        for mode in ('dry','lint'):
            r=run(mode=mode,data=b'',paths=[folder]);assert r['returncode']==(1 if mode=='lint' else 0)
        for values,patterns in [({'-match_type':'doublestar'},'**/*.yaml'),({'-match_type':'gitignore'},'yamlfmt.patterns'),({'-exclude':'nested'},''),({'-gitignore_excludes':True},''),({'-extensions':'tpl'},'')]:
            r=run(data=b'',paths=[folder],values=values,patterns=patterns);assert r['returncode']==0,(values,r)
            names=zipfile.ZipFile(io.BytesIO(r['stdout'])).namelist()
            if values.get('-extensions'):assert any(n.endswith('.tpl') for n in names)
            if values.get('-exclude') or values.get('-gitignore_excludes') or values.get('-match_type')=='gitignore':assert not any(n.startswith('nested/') for n in names),(values,names)
            if values.get('-match_type')=='doublestar':assert names==['demo.yaml'],names
        assert json.loads(run(mode='dry',data=b'',paths=[folder],values={'-output_format':'gitlab'})['stdout'])
        for patterns in ('../outside.yaml','C:/outside.yaml','/outside.yaml'):
            try:run(data=b'',paths=[folder],patterns=patterns)
            except ValueError:pass
            else:raise AssertionError('Escaping pattern accepted')
        assert all(hashlib.sha256(f.read_bytes()).hexdigest()==sha for f,sha in snapshot.items())
        (folder/'bad.yaml').write_bytes(b'bad: [')
        failed=run(data=b'',paths=[folder]);assert failed['returncode']!=0 and failed.get('extension')!='.zip'
        partial=run(data=b'',paths=[folder],values={'-continue_on_error':True});assert partial['returncode']==0 and partial['stderr']
        ignored=run(data=b'',paths=[folder],config='{"regex_exclude":["bad: "]}');assert ignored['returncode']==0
        (folder/'yamlfmt.patterns').write_text('../outside.yaml\n',encoding='utf8')
        try:run(data=b'',paths=[folder],values={'-match_type':'gitignore'},patterns='yamlfmt.patterns')
        except ValueError:pass
        else:raise AssertionError('Escaping pattern file accepted')
        outside=p/'outside';outside.mkdir();(outside/'private.yaml').write_bytes(b'private:\n x: 1\n')
        junction=folder/'link'
        subprocess.run(['cmd','/c','mklink','/J',str(junction),str(outside)],capture_output=True,check=True)
        try:
            try:run(data=b'',paths=[folder])
            except ValueError:pass
            else:raise AssertionError('Junction accepted')
        finally:junction.rmdir()
    event=threading.Event();event.set()
    try:execute_job(str(EXE),[],b'a: 1\n',event,'format',[],'{}','')
    except InterruptedError:pass
    else:raise AssertionError('Cancelled job ran')
    print('PASS',count,'CLI/formatter/mode/pattern/config checks, Unicode paths, original preservation and cancellation',flush=True)
def settle(a):
    end=time.monotonic()+30
    while time.monotonic()<end:
        a.root.update();time.sleep(.03)
        if not a.worker.is_alive() and a.q.empty():break
    assert a.last_result and 'stdout' in a.last_result,a.last_result
def gui():
    from unittest.mock import patch
    from PIL import ImageGrab
    m=load();a=m.App(PROFILE,APP);a.exe_path=str(EXE);a.advanced.exe_path=str(EXE)
    try:
        a.in_text.insert('1.0','app:\n name: kiwi\n list: [a,b]\n');a.values['@f.indent'].set('4');a.values['@line_ending'].set('lf')
        a.run();settle(a);assert b'    name' in a.last_result['stdout']
        public=Path('C:/Users/Public/Documents/kiwi-yamlfmt-demo');public.mkdir(exist_ok=True)
        saved=public/'saved.yaml'
        with patch('workbench.filedialog.asksaveasfilename',return_value=str(saved)),patch('workbench.messagebox.askyesno',return_value=True):a._save()
        assert saved.read_bytes()==a.last_result['stdout']
        a.root.update();u=ctypes.windll.user32;u.GetAncestor.argtypes=[ctypes.c_void_p,ctypes.c_uint];u.GetAncestor.restype=ctypes.c_void_p
        ImageGrab.grab(window=u.GetAncestor(a.root.winfo_id(),2)).save(ROOT/'site/assets/screenshots/kiwi-yamlfmt-public.png')
        a.advanced.open_window();a.root.update();assert a.advanced.option_tree.get_children();a.advanced._on_toplevel_close();a.root.update()
        a.mode_var.set('有効な設定を表示');a.run();settle(a);assert b'indent: 4' in a.last_result['stdout']
        conf=public/'settings.yaml'
        with patch.object(m.filedialog,'asksaveasfilename',return_value=str(conf)):a.save_config()
        a.read_config(conf);assert 'formatter' in a.config_text.get('1.0','end-1c')
        a.mode_var.set('整形チェック');a.run();settle(a);assert a.last_result.get('status')=='differences'
        report=public/'report.txt'
        with patch('workbench.filedialog.asksaveasfilename',return_value=str(report)),patch('workbench.messagebox.askyesno',return_value=True):a._save()
        assert report.read_bytes()==a.last_result['stdout']
        a.mode_var.set('バージョン');a.run();settle(a);assert b'0.21.0' in a.last_result['stdout']
        print('PASS native GUI formatting/save/config/version and advanced controls, screenshot',flush=True)
    finally:a._on_close()
def portable():
    from verify_advanced_zip import wait_window,user32,windows
    from PyInstaller.archive.readers import CArchiveReader
    pin=json.loads((APP/'upstream-pin.json').read_text(encoding='utf8'));pkg=APP/'KiwiYamlfmt-0.1.0-win11-x64.zip'
    with zipfile.ZipFile(pkg) as z,tempfile.TemporaryDirectory() as td:
        assert {'README.txt','LICENSE','UPSTREAM-LICENSE.txt','THIRD-PARTY-NOTICES.txt','Runtime-LICENSES.txt'}<=set(z.namelist())
        z.extractall(td);exe=Path(td)/'KiwiYamlfmt.exe'
        embedded=CArchiveReader(str(exe)).extract('yamlfmt.exe');assert hashlib.sha256(embedded).hexdigest()==pin['binary_sha']
        existing=windows();proc=subprocess.Popen([str(exe)],cwd=td)
        try:
            hwnd=wait_window('きういYAML整形',existing);end=time.monotonic()+5
            while not user32.GetMenu(hwnd) and time.monotonic()<end:time.sleep(.05)
            menu=user32.GetMenu(hwnd);sub=user32.GetSubMenu(menu,0);command=user32.GetMenuItemID(sub,0)
            user32.PostMessageW(hwnd,0x111,command,0);detail=wait_window('yamlfmt.exe - 詳細機能',existing)
            user32.PostMessageW(detail,0x10,0,0);time.sleep(.2);user32.PostMessageW(hwnd,0x10,0,0);proc.wait(timeout=15);assert proc.returncode==0;time.sleep(.3)
        finally:
            if proc.poll() is None:
                subprocess.run(['taskkill','/F','/T','/PID',str(proc.pid)],capture_output=True);proc.wait(timeout=10)
    print('PASS extracted ZIP notices/binary, native and detailed GUI, clean exit',flush=True)
if __name__=='__main__':globals()[sys.argv[1]]()
