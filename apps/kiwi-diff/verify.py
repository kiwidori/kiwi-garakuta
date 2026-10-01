"""Verify real difftastic comparisons and Windows GUI actions."""
import hashlib
import importlib.util
import sys
import threading
import time
from pathlib import Path
from PIL import ImageGrab
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
sys.path.insert(0,str(HERE))
import core

def wait(app):
    deadline=time.monotonic()+25
    while app.running and time.monotonic()<deadline:
        app.update()
        time.sleep(0.05)
    app.update()
    assert not app.running

def main():
    folder=Path('C:/Users/Public/Documents/kiwi-diff-demo')
    folder.mkdir(exist_ok=True)
    left,right=folder/'変更前.json',folder/'変更後.json'
    left.write_text('{\n  "name": "Kiwi",\n  "limit": 100,\n  "theme": "light"\n}\n',encoding='utf8')
    right.write_text('{\n  "name": "Kiwi",\n  "limit": 200,\n  "theme": "dark",\n  "enabled": true\n}\n',encoding='utf8')
    before={p:hashlib.sha256(p.read_bytes()).hexdigest() for p in (left,right)}
    exe=ROOT/'.tools/difft/difft.exe'
    def run(a=left,b=right,plain=False):
        return core.compare_files(exe,a,b,plain,threading.Event())
    result=run()
    assert result['changed'] and '100' in result['text'] and '200' in result['text'] and '\x1b' not in result['text']
    assert not run(left,left)['changed']
    whitespace=folder/'formatting.json'
    whitespace.write_text('{"name":"Kiwi","limit":100,"theme":"light"}\n',encoding='utf8')
    assert not run(left,whitespace)['changed']
    assert run(left,whitespace,True)['changed']
    bom=folder/'bom.json'
    bom.write_bytes(b'\xef\xbb\xbf'+left.read_bytes().replace(b'\n',b'\r\n'))
    assert not run(left,bom,True)['changed']
    invalid=folder/'binary.txt'
    invalid.write_bytes(b'\x00data')
    for bad in (invalid,folder,folder/'missing.txt'):
        try:
            run(bad,right)
        except ValueError:
            pass
        else:
            raise AssertionError('Bad input accepted')
    invalid.write_bytes(b'\x82\xa0')
    try:
        run(invalid,right)
    except ValueError:
        pass
    else:
        raise AssertionError('Non-UTF8 accepted')
    original=core.subprocess.Popen
    children=[]
    def slow_child(_cmd,**kwargs):
        child=original([sys.executable,'-c','import time;time.sleep(30)'],**kwargs)
        children.append(child)
        return child
    core.subprocess.Popen=slow_child
    event=threading.Event()
    timer=threading.Timer(0.2,event.set)
    timer.start()
    try:
        core.compare_files(exe,left,right,False,event)
    except InterruptedError:
        assert children[0].poll() is not None
    else:
        raise AssertionError('Cancellation ignored')
    finally:
        timer.cancel()
        core.subprocess.Popen=original
    spec=importlib.util.spec_from_file_location('kiwi_diff',HERE/'main.py')
    module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.resource_dir=lambda:exe.parent
    app=module.App()
    try:
        app.update()
        time.sleep(0.2)
        app.update()
        app.left.set(str(left))
        app.right.set(str(right))
        app.start_compare()
        wait(app)
        assert app.output.get('1.0','end-1c')==result['text'],app.status.get()
        assert app.output.tag_ranges('removed') and app.output.tag_ranges('added')
        app.copy_output()
        assert app.clipboard_get()==result['text']
        destination=folder/'比較結果.txt'
        module.filedialog.asksaveasfilename=lambda **kwargs:str(destination)
        app.save_output()
        assert destination.read_bytes()==result['text'].encode('utf8')
        module.filedialog.asksaveasfilename=lambda **kwargs:str(left)
        app.save_output()
        assert all(hashlib.sha256(p.read_bytes()).hexdigest()==before[p] for p in before)
        app.status.set('差分あり')
        app.geometry('1000x720+100+100')
        app.attributes('-topmost',True)
        app.update()
        app.lift()
        time.sleep(0.3)
        x,y=app.winfo_rootx(),app.winfo_rooty()
        ImageGrab.grab(bbox=(x,y,x+app.winfo_width(),y+app.winfo_height())).save(ROOT/'site/assets/screenshots/kiwi-diff-public.png')
        app.plain.set(True)
        assert not app.output.get('1.0','end-1c')
        def slow(_exe,_left,_right,_plain,event):
            assert event.wait(5)
            raise InterruptedError()
        module.compare_files=slow
        app.start_compare()
        app.update()
        app.stop_compare()
        wait(app)
        assert '停止' in app.status.get()
    finally:
        app.close()
    print('PASS: actual changed/equal/syntax/plain/CRLF/BOM comparison, invalid UTF8/binary/path, child stop, GUI/copy/save and original preservation')

if __name__=='__main__':
    main()
