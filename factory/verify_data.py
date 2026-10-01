"""Real Windows workflows and GUI/portable checks for the dasel wrapper."""
import argparse,ctypes,hashlib,importlib.util,json,os,subprocess,sys,tempfile,time,zipfile
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]; APP=ROOT/'apps/kiwi-data'; EXE=ROOT/'.tools/dasel/dasel.exe'
sys.path.insert(0,str(ROOT/'apps/common'))
import runtime
PROFILE=json.loads((APP/'profile.json').read_text(encoding='utf8'))
DEMO={'items':[{'name':'A','n':2},{'name':'B','n':1}],'title':'kiwi'}
def invoke(data,query='',fmt='json',out='json',extra=()):
    result=runtime.execute(str(EXE),['query','--config','NUL','--in',fmt,'--out',out,*extra,'--',query],stdin_data=data.encode())
    assert result['returncode']==0,result['stderr']
    return result['stdout']
def cli():
    assert hashlib.sha256(EXE.read_bytes()).hexdigest()==json.loads((APP/'upstream-pin.json').read_text(encoding='utf8'))['binary_sha']
    checks=0
    cases=[('$this',DEMO),('items.map(name)',['A','B']),('items.filter(n>1)',[DEMO['items'][0]]),('items.sortBy(n)',list(reversed(DEMO['items']))),('items.groupBy(name)',{'A':[DEMO['items'][0]],'B':[DEMO['items'][1]]}),('items.reduce(n,0,$acc+$this)',3),('..name',['A','B']),('search(n==2)',[DEMO['items'][0]]),('items.any(n==2)',True),('items.all(n>0)',True),('items.count(n>1)',1),('items.map({label:name,value:n})',[{'label':'A','value':2},{'label':'B','value':1}]),('title.toUpper()','KIWI'),('items.map(name).join(",")','A,B'),('items.first()',DEMO['items'][0]),('items.map({name:name})',[{'name':'A'},{'name':'B'}])]
    text=json.dumps(DEMO)
    for query,expected in cases:
        assert json.loads(invoke(text,query))==expected,query; checks+=1
    assert json.loads(invoke(text,'title=$changed',extra=['--root','--var','changed=json:"日本語"']))['title']=='日本語';checks+=1
    assert json.loads(invoke(text,'$x',extra=['--var','x=json:{"v":2}']))=={'v':2};checks+=1
    assert json.loads(invoke(text,'$x=2;$x+3',extra=['--unstable']))==5;checks+=1
    assert b'\n' not in invoke(text,'',extra=['--compact']).strip();checks+=1
    for fmt,inp in [('yaml','name: Kiwi\nvalue: 2\n'),('toml','name="Kiwi"\nvalue=2'),('csv','name,value\nKiwi,2\n'),('xml','<root><name>Kiwi</name></root>'),('ini','[main]\nname=Kiwi\n'),('hcl','name="Kiwi"\n'),('kdl','name "Kiwi"'),('dasel','{name:"Kiwi",value:2}')]:
        assert b'Kiwi' in invoke(inp,fmt=fmt);checks+=1
    # Verify actual writers with inputs they can represent; CSV/XML/INI/HCL are not arbitrary JSON containers.
    for fmt in ['json','yaml','toml','xml','hcl','ini','kdl']:
        assert invoke('{"name":"Kiwi","value":"2"}',out=fmt).strip();checks+=1
    assert b'Kiwi' in invoke('[{"name":"Kiwi","value":"2"}]',out='csv');checks+=1
    assert json.loads(invoke('name;value\nKiwi;2\n',fmt='csv',extra=['--read-flag','csv-delimiter=;']))[0]['name']=='Kiwi';checks+=1
    assert b';' in invoke('[{"name":"Kiwi","value":"2"}]',out='csv',extra=['--write-flag','csv-delimiter=;']);checks+=1
    assert b';' in invoke('name;value\nKiwi;2\n',fmt='csv',out='csv',extra=['--rw-flag','csv-delimiter=;']);checks+=1
    assert b'root' in invoke('<root><name>Kiwi</name></root>',fmt='xml',extra=['--read-flag','xml-mode=structured']);checks+=1
    assert b'Kiwi' in invoke('{"name":"Kiwi"}',out='kdl',extra=['--write-flag','kdl-version=1']);checks+=1
    nd=invoke('{"v":1}\n{"v":2}\n','v');assert [json.loads(s) for s in nd.splitlines() if s.strip()]==[1,2];checks+=1
    assert b'Kiwi' in invoke('name: Kiwi\n---\nname: Kiwi\n',fmt='yaml');checks+=1
    with tempfile.TemporaryDirectory() as td:
        path=Path(td)/'data.json';path.write_text('{"name":"Kiwi"}',encoding='utf8')
        before=path.read_bytes()
        assert json.loads(invoke('null','$file',extra=['--var',f'file=json:file:{path}']))=={'name':'Kiwi'};checks+=1
        expr='parse("json",readFile('+json.dumps(str(path))+'))'
        assert json.loads(invoke('null',expr))=={'name':'Kiwi'};assert before==path.read_bytes();checks+=1
        config=Path(td)/'settings.yaml';config.write_text('default_format: yaml\n',encoding='utf8')
        result=runtime.execute(str(EXE),['query','--config',str(config),'--in','json','--out','yaml','--','$this'],stdin_data=b'{"value":2}')
        assert result['returncode']==0 and b'value: 2' in result['stdout'];checks+=1
    with patch.dict(os.environ,KIWI_DATA_DEMO_VALUE='Kiwi'):
        assert json.loads(invoke('null','$KIWI_DATA_DEMO_VALUE'))=='Kiwi';checks+=1
    for args in [['version'],['completion','powershell'],['man'],['query','--help']]:
        r=runtime.execute(str(EXE),args);assert r['returncode']==0 and r['stdout'];checks+=1
    for args in [['interactive'],['query','--it'],['query','--it=true']]:
        try:runtime.build_command(str(EXE),args,blocked_flags=PROFILE['blocked_flags'])
        except ValueError:pass
        else:raise AssertionError('TTY mode must be blocked')
    print('PASS',checks,'real CLI transformations, query families, flags and information commands')
def app_module():
    spec=importlib.util.spec_from_file_location('kiwi_data_main',APP/'main.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
def settle(app):
    deadline=time.monotonic()+25
    while app.worker and app.worker.is_alive() and time.monotonic()<deadline:
        app.root.update();time.sleep(.025)
    for _ in range(4):app.root.update();time.sleep(.1)
    assert not (app.worker and app.worker.is_alive()),'GUI worker stuck'
    assert app.last_result and app.last_result.get('returncode')==0,app.last_result
def gui():
    from PIL import ImageGrab
    ctypes.windll.user32.SetProcessDPIAware()
    m=app_module();app=m.DataApp(PROFILE,APP);app.exe_path=str(EXE);app.root.geometry('1100x850+40+30')
    try:
        app._load_demo();assert json.loads(app.in_text.get('1.0','end'))==DEMO;app.root.update()
        # Every displayed example must run against the displayed demo, not just show plausible syntax.
        for example in app.ex_combo['values']:
            app.ex_combo.set(example);app._apply_example();app.run();settle(app)
        app.query_text.delete('1.0','end');app.values['--out'].set('yaml');app.run();settle(app)
        assert b'items:' in app.last_result['stdout']
        app.values['--out'].set('json')
        demo=Path('C:/Users/Public/Documents/kiwi-data-demo');demo.mkdir(exist_ok=True)
        cfg=demo/'settings.yaml';cfg.write_text('default_format: json\n',encoding='utf8')
        with patch.object(m.filedialog,'askopenfilename',return_value=str(cfg)):app._choose_config()
        assert app.values['--config'].get()==str(cfg);app.values['--config'].set('NUL')
        src=demo/'日本語.json';src.write_bytes(b'\xef\xbb\xbf'+json.dumps(DEMO,ensure_ascii=False).encode())
        before=hashlib.sha256(src.read_bytes()).digest()
        with patch.object(m.filedialog,'askopenfilename',return_value=str(src)):app._load_file()
        assert 'items' in app.in_text.get('1.0','end');assert before==hashlib.sha256(src.read_bytes()).digest()
        invalid=demo/'invalid.json';invalid.write_bytes(b'\xff');large=demo/'large.json';large.write_bytes(b'x'*(2*1024*1024+1))
        previous=app.in_text.get('1.0','end')
        for path in (invalid,large):
            with patch.object(m.filedialog,'askopenfilename',return_value=str(path)),patch.object(m.messagebox,'showerror') as err:
                app._load_file();assert err.called;assert previous==app.in_text.get('1.0','end')
        app.query_text.delete('1.0','end');app.query_text.insert('1.0','items.sortBy(n).map({name:name,value:n})');app.run();settle(app)
        assert json.loads(app.last_result['stdout'])==[{'name':'B','value':1},{'name':'A','value':2}]
        save=demo/'result.json'
        with patch('workbench.filedialog.asksaveasfilename',return_value=str(save)),patch('workbench.messagebox.askyesno',return_value=True):app._save()
        assert save.read_bytes()==app.last_result['stdout']
        assert app.query_text.winfo_viewable(),'Query must be initial visible tab'
        app.ex_combo.set('')
        app.root.lift();app.root.update();time.sleep(.3);x,y=app.root.winfo_rootx(),app.root.winfo_rooty()
        user32=ctypes.windll.user32;user32.GetAncestor.argtypes=[ctypes.c_void_p,ctypes.c_uint];user32.GetAncestor.restype=ctypes.c_void_p
        hwnd=user32.GetAncestor(app.root.winfo_id(),2)
        ImageGrab.grab(window=hwnd).save(ROOT/'site/assets/screenshots/kiwi-data-public.png')
        app.advanced.exe_path=str(EXE);app.advanced.open_window();app.root.update();assert app.advanced.option_tree.get_children()
        app.advanced._on_toplevel_close();app.root.update()
        app.mode_var.set('バージョン');app.in_text.delete('1.0','end');app.run();settle(app);assert b'3.11.2' in app.last_result['stdout']
        print('PASS GUI examples, BOM file load, byte cap, invalid encoding, saved bytes, advanced window, version')
    finally:app._on_close()
def portable():
    from verify_advanced_zip import windows,wait_window,user32
    from PyInstaller.archive.readers import CArchiveReader
    pin=json.loads((APP/'upstream-pin.json').read_text(encoding='utf8'));pkg=APP/f"{pin['app_exe']}-{pin['version']}-win11-x64.zip"
    with zipfile.ZipFile(pkg) as z,tempfile.TemporaryDirectory() as td:
        assert {'README.txt','LICENSE','UPSTREAM-LICENSE.txt','THIRD-PARTY-NOTICES.txt','Runtime-LICENSES.txt'}<=set(z.namelist());z.extractall(td)
        exe=Path(td)/'KiwiData.exe';a=CArchiveReader(str(exe));assert json.loads(a.extract('profile.json'))==PROFILE
        assert hashlib.sha256(a.extract('dasel.exe')).hexdigest()==pin['binary_sha'];assert 'workbench_jobs' in a.open_embedded_archive('PYZ.pyz').toc
        existing=windows();proc=subprocess.Popen([str(exe)])
        try:
            root=wait_window(PROFILE['title'],existing);sub=user32.GetSubMenu(user32.GetMenu(root),0)
            user32.PostMessageW(root,0x0111,user32.GetMenuItemID(sub,0),0);detail=wait_window('dasel.exe - 詳細機能',existing)
            user32.PostMessageW(detail,0x0010,0,0);time.sleep(.2);user32.PostMessageW(root,0x0010,0,0);proc.wait(timeout=12);assert proc.returncode==0
        finally:
            if proc.poll() is None:subprocess.run(['taskkill','/F','/T','/PID',str(proc.pid)],capture_output=True)
    print('PASS portable ZIP extraction, licenses, pinned binary, frozen GUI and advanced, close')
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('stage',choices=['cli','gui','portable']);globals()[p.parse_args().stage]()

