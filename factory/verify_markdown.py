"""Windows execution, styled display and portable ZIP checks for Glow GUI."""
import ctypes,hashlib,importlib.util,json,os,sys,tempfile,threading,time,zipfile,subprocess
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1];APP=ROOT/'apps/kiwi-markdown';EXE=ROOT/'.tools/glow/glow.exe'
sys.path.insert(0,str(ROOT/'apps/common'))
import runtime
PROFILE=json.loads((APP/'profile.json').read_text(encoding='utf8'))
DEMO='# きういMarkdown\n\n**太字**と*斜体*、`コード`\n\n| 項目 | 値 |\n| --- | --- |\n| 例 | 42 |\n\n```python\nprint("hello")\n```\n'
class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200);self.send_header('Content-Type','text/markdown; charset=utf-8');self.end_headers();self.wfile.write(DEMO.encode())
    def log_message(self,*args):pass
def server():
    srv=ThreadingHTTPServer(('127.0.0.1',0),Handler);threading.Thread(target=srv.serve_forever,daemon=True).start();return srv
def invoke(args,data=b'',timeout=30):
    r=runtime.execute(str(EXE),args,stdin_data=data,timeout=timeout,blocked_flags=PROFILE['blocked_flags'])
    assert r['returncode']==0,r['stderr'];return r
def cli():
    pin=json.loads((APP/'upstream-pin.json').read_text(encoding='utf8'));assert hashlib.sha256(EXE.read_bytes()).hexdigest()==pin['binary_sha']
    for style in ['light','dark','ascii','tokyo-night','notty','auto']:
        r=invoke(['--style',style,'--width','70'],DEMO.encode());assert '太字' in runtime._strip_ansi(r['stdout'].decode())
    for width in ['0','35','100']:
        assert b'hello' in invoke(['--style','light','--width',width,'--preserve-new-lines'],DEMO.encode())['stdout']
    demo=Path('C:/Users/Public/Documents/kiwi-markdown-demo');demo.mkdir(exist_ok=True);src=demo/'日本語.md';src.write_text(DEMO,encoding='utf8')
    before=src.read_bytes();r=invoke(['--style','light','--',str(src)],None);assert '太字' in runtime._strip_ansi(r['stdout'].decode());assert before==src.read_bytes()
    custom=demo/'style.json';custom.write_text('{"document":{"block_prefix":"START\\n","block_suffix":"\\nEND","margin":0}}',encoding='utf8')
    assert b'START' in invoke(['--style',str(custom)],b'# hello')['stdout']
    srv=server()
    try:assert b'hello' in invoke(['--style','light','--',f'http://127.0.0.1:{srv.server_port}/demo.md'],None)['stdout']
    finally:srv.shutdown();srv.server_close()
    for args in [['--version'],['--help'],['man'],['completion','powershell'],['completion','bash'],['completion','zsh'],['completion','fish']]:assert invoke(args)['stdout']
    # Guard against opening the TUI from empty data or a directory and against inherited external commands.
    for args in [[],['--style','light'],['--',str(demo)],['--pager'],['-p'],['--pager=false'],['--tui'],['--config','bad.yml'],['config']]:
        try:runtime.execute(str(EXE),args,blocked_flags=PROFILE['blocked_flags'],timeout=2)
        except ValueError:pass
        else:raise AssertionError(args)
    with patch.dict(os.environ,GLOW_PAGER='true',GLOW_TUI='true',GLOW_STYLE='does-not-exist',GLAMOUR_STYLE='does-not-exist',PAGER='does-not-exist'):
        assert b'hello' in invoke(['--style','light'],b'# hello')['stdout']
    print('PASS styles, wrap/newlines, Japanese file, custom JSON, HTTP, help/man/completions, unsafe flags and environment isolation')
def module():
    spec=importlib.util.spec_from_file_location('kiwi_markdown_main',APP/'main.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
def settle(app):
    deadline=time.monotonic()+30
    while app.worker and app.worker.is_alive() and time.monotonic()<deadline:app.root.update();time.sleep(.025)
    for _ in range(4):app.root.update();time.sleep(.1)
    assert not(app.worker and app.worker.is_alive());assert app.last_result and app.last_result.get('returncode')==0,app.last_result
def gui():
    from PIL import ImageGrab
    ctypes.windll.user32.SetProcessDPIAware();m=module();app=m.MarkdownApp(PROFILE,APP);app.exe_path=str(EXE);app.root.geometry('1100x850+40+30')
    demo=Path('C:/Users/Public/Documents/kiwi-markdown-demo');demo.mkdir(exist_ok=True);src=demo/'日本語.md';src.write_text(DEMO,encoding='utf8')
    try:
        app.in_text.insert('1.0',DEMO);app.run();settle(app)
        shown=app.out_text.get('1.0','end');assert '太字' in shown and 'hello' in shown and '\x1b' not in shown
        assert any(x[0]=='tagon' for x in app.out_text.dump('1.0','end',tag=True,text=False)),'ANSI styles must be actual Text tags'
        raw=app.last_result['stdout'];save=demo/'rendered.ansi.txt'
        with patch('workbench.filedialog.asksaveasfilename',return_value=str(save)),patch('workbench.messagebox.askyesno',return_value=True):app._save()
        assert save.read_bytes()==raw
        plain=demo/'rendered.txt'
        with patch.object(m.filedialog,'asksaveasfilename',return_value=str(plain)),patch.object(m.messagebox,'askyesno',return_value=True):app._save_plain()
        assert plain.read_text(encoding='utf8')==runtime._strip_ansi(raw.decode('utf8'))
        custom=demo/'style.json';custom.write_text('{"document":{"block_prefix":"START\\n","block_suffix":"\\nEND","margin":0}}',encoding='utf8')
        with patch.object(m.filedialog,'askopenfilename',return_value=str(custom)):app._choose_style()
        assert app.values['--style'].get()==str(custom);app.run();settle(app);assert 'START' in app.out_text.get('1.0','end')
        app._set_theme('dark');app.run();settle(app);assert app.out_text.cget('background')=='#1e1e2e'
        app._set_theme('light')
        large=demo/'large.md';large.write_bytes(b'x'*(2*1024*1024+1))
        for args,data,mode in [(['--',str(large)],None,{'files':True}),(['--',str(src),str(src)],None,{'files':True}),([],b'file:///private',{'url':True}),([],b'http://example.org/with space',{'url':True})]:
            app._worker(args,data,mode);item=app.q.get_nowait();assert item[0]=='error',item
        app.mode_var.set('ファイルを表示');app.in_text.delete('1.0','end');app.paths=[str(src)];app.path_list.insert('end',str(src));app.run();settle(app);assert '太字' in app.out_text.get('1.0','end')
        app.paths=[];app.path_list.delete(0,'end');app.mode_var.set('URL・リポジトリREADMEを表示');srv=server()
        try:app.in_text.insert('1.0',f'http://127.0.0.1:{srv.server_port}/demo.md');app.run();settle(app);assert 'hello' in app.out_text.get('1.0','end')
        finally:srv.shutdown();srv.server_close()
        # SGR state, resets, rich colors and OSC must be handled without executing any control action.
        m.render_ansi(app.out_text,'\x1b[1;38;2;255;0;0mBOLD\x1b[0m normal \x1b[3;4;38;5;33mSTYLE\x1b[0m\x1b]8;;https://example.invalid\x07LINK\x1b]8;;\x07')
        assert app.out_text.get('1.0','end').strip()=='BOLD normal STYLELINK'
        tags=app.out_text.tag_names('1.0');assert any(app.out_text.tag_cget(t,'foreground')=='#ff0000' for t in tags)
        m.render_ansi(app.out_text,('\x1b[31mR\x1b[0mN')*1000)
        tags=app.out_text.tag_names('1.1998');assert any(app.out_text.tag_cget(t,'foreground')=='#800000' for t in tags),'Repeated styles must remain styled after 256 spans'
        assert len([t for t in app.out_text.tag_names() if t.startswith('glow_')])<=256
        m.render_ansi(app.out_text,'\x1b[9mSTRIKE\x1b[29m NORMAL')
        assert any(app.out_text.tag_cget(t,'overstrike')=='1' for t in app.out_text.tag_names('1.0'))
        assert all(app.out_text.tag_cget(t,'overstrike') in ('0','') for t in app.out_text.tag_names('1.7'))
        m.render_ansi(app.out_text,''.join(f'\x1b[38;5;{i};48;5;{15-i}mX' for i in range(16)))
        assert app.out_text.get('1.0','end').strip()=='X'*16
        app.out_text.configure(background='#1e1e2e',foreground='#ffffff');m.render_ansi(app.out_text,'normal')
        assert all(app.out_text.tag_cget(t,'background')=='#1e1e2e' for t in app.out_text.tag_names('1.0') if t.startswith('glow_'))
        m.render_ansi(app.out_text,'日'*100000);assert len(app.out_text.get('1.0','end').encode())<132000
        app.out_text.configure(background='#ffffff',foreground='#000000')
        app.mode_var.set('貼り付けたMarkdownを表示');app.in_text.delete('1.0','end');app.in_text.insert('1.0','~~削除線~~');app.run();settle(app)
        pos=app.out_text.search('削除線','1.0');assert pos
        assert any(app.out_text.tag_cget(t,'overstrike')=='1' for t in app.out_text.tag_names(pos))
        app._load_demo();assert app.mode_var.get()=='貼り付けたMarkdownを表示';assert not app.paths;app.run();settle(app)
        app.root.update();user32=ctypes.windll.user32;user32.GetAncestor.argtypes=[ctypes.c_void_p,ctypes.c_uint];user32.GetAncestor.restype=ctypes.c_void_p
        ImageGrab.grab(window=user32.GetAncestor(app.root.winfo_id(),2)).save(ROOT/'site/assets/screenshots/kiwi-markdown-public.png')
        app.advanced.exe_path=str(EXE);app.advanced.open_window();app.root.update();assert app.advanced.option_tree.get_children();app.advanced._on_toplevel_close();app.root.update()
        app.mode_var.set('バージョン');app.in_text.delete('1.0','end');app.run();settle(app);assert b'3.0.0' in app.last_result['stdout']
        print('PASS native styled Markdown, file and URL GUI jobs, raw save bytes, SGR/OSC, screenshot, advanced, version')
    finally:app._on_close()
def portable():
    from verify_advanced_zip import windows,wait_window,user32
    from PyInstaller.archive.readers import CArchiveReader
    pin=json.loads((APP/'upstream-pin.json').read_text(encoding='utf8'));pkg=APP/f"{pin['app_exe']}-{pin['version']}-win11-x64.zip"
    with zipfile.ZipFile(pkg) as z,tempfile.TemporaryDirectory() as td:
        assert {'README.txt','LICENSE','UPSTREAM-LICENSE.txt','THIRD-PARTY-NOTICES.txt','Runtime-LICENSES.txt'}<=set(z.namelist());z.extractall(td)
        exe=Path(td)/'KiwiMarkdown.exe';a=CArchiveReader(str(exe));assert json.loads(a.extract('profile.json'))==PROFILE;assert hashlib.sha256(a.extract('glow.exe')).hexdigest()==pin['binary_sha']
        existing=windows();proc=subprocess.Popen([str(exe)])
        try:
            root=wait_window(PROFILE['title'],existing);sub=user32.GetSubMenu(user32.GetMenu(root),0);user32.PostMessageW(root,0x0111,user32.GetMenuItemID(sub,0),0)
            detail=wait_window('glow.exe - 詳細機能',existing);user32.PostMessageW(detail,0x0010,0,0);time.sleep(.2);user32.PostMessageW(root,0x0010,0,0);proc.wait(timeout=12);assert proc.returncode==0
        finally:
            if proc.poll() is None:subprocess.run(['taskkill','/F','/T','/PID',str(proc.pid)],capture_output=True)
    print('PASS portable ZIP licenses, pinned binary, native and advanced frozen GUI, close')
if __name__=='__main__':
    stage=sys.argv[1];globals()[stage]()
