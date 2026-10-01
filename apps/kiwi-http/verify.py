"""Test xh against a local HTTP fixture, then verify the Windows GUI."""
import sys
import re
import time
import threading
import importlib.util
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from PIL import ImageGrab

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
sys.path.insert(0,str(HERE))
import core

requests=[]
class Handler(BaseHTTPRequestHandler):
    def log_message(self,*args):
        pass
    def do_HEAD(self):
        self.send_response(200)
        self.send_header('X-Demo','KiwiHTTP')
        self.end_headers()
    def do_GET(self):
        requests.append(self.path)
        if self.path=='/slow':
            time.sleep(3)
        code=404 if self.path=='/missing' else 302 if self.path=='/redirect' else 200
        self.send_response(code)
        self.send_header('Content-Type','application/json; charset=utf-8')
        if self.path=='/redirect':
            self.send_header('Location','/redirect-target')
        self.end_headers()
        try:
            body=(b'x'*600000) if self.path=='/large' else '{"message":"こんにちは","tool":"Kiwi HTTP"}'.encode('utf-8')
            self.wfile.write(body)
        except (BrokenPipeError,ConnectionResetError,ConnectionAbortedError):
            pass

def wait(app):
    deadline=time.monotonic()+20
    while app.running and time.monotonic()<deadline:
        app.update()
        time.sleep(0.05)
    app.update()
    assert not app.running,'GUI timeout'

def main():
    exe=ROOT/'.tools/xh/xh-v0.26.2-x86_64-pc-windows-msvc/xh.exe'
    server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
    thread=threading.Thread(target=server.serve_forever,daemon=True)
    thread.start()
    base=f'http://127.0.0.1:{server.server_port}'
    try:
        def run(path,method='GET'):
            return core.request(exe,base+path,method,threading.Event())
        result=run('/demo?query=日本語')
        assert '200 OK' in result and 'こんにちは' in result
        assert 'X-Demo: KiwiHTTP'.lower() in run('/demo','HEAD').lower()
        assert 'こんにちは' not in run('/demo','HEAD')
        assert '404' in run('/missing')
        assert '302' in run('/redirect')
        assert '/redirect-target' not in requests,'Redirect was followed'
        for url in ['', 'file:///test', 'https://user:pass@example.com', 'http://example.com:invalid', 'http://example.com/a b', 'http://example.com/\n', '--help']:
            try:
                core.validate_url(url)
            except ValueError:
                pass
            else:
                raise AssertionError('Unsafe URL accepted')
        try:
            run('/large')
        except ValueError as error:
            assert '512' in str(error)
        else:
            raise AssertionError('Large response accepted')
        stop=threading.Event()
        timer=threading.Timer(0.2,stop.set)
        timer.start()
        started=time.monotonic()
        try:
            core.request(exe,base+'/slow','GET',stop)
        except InterruptedError:
            assert time.monotonic()-started<2,'Cancellation too slow'
        else:
            raise AssertionError('Cancellation ignored')
        timer.cancel()
        spec=importlib.util.spec_from_file_location('kiwi_http',HERE/'main.py')
        module=importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        module.resource_dir=lambda:exe.parent
        app=module.App()
        try:
            app.url.set(base+'/demo')
            app.method.set('GET')
            app.start_request()
            wait(app)
            value=app.output.get('1.0','end-1c')
            assert 'こんにちは' in value,app.status.get()
            app.copy_output()
            assert app.clipboard_get()==value
            app.geometry('980x620+100+100')
            app.attributes('-topmost',True)
            app.update()
            app.lift()
            time.sleep(0.4)
            x,y=app.winfo_rootx(),app.winfo_rooty()
            ImageGrab.grab(bbox=(x,y,x+app.winfo_width(),y+app.winfo_height())).save(ROOT/'site/assets/screenshots/kiwi-http-public.png')
            app.url.set(base+'/slow')
            app.start_request()
            app.update()
            app.stop_request()
            wait(app)
            assert '停止' in app.status.get()
        finally:
            app.close()
        print('PASS: actual GET/HEAD, Unicode response, 404, no redirect follow, URL validation, output bounds, stop and GUI copy')
    finally:
        server.shutdown()
        server.server_close()

if __name__=='__main__':
    main()
