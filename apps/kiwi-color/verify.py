"""Test actual pastel conversions and capture the Windows color GUI."""
from pathlib import Path
import sys
import threading
import time
import importlib.util
from PIL import ImageGrab
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
sys.path.insert(0,str(HERE))
import core

def wait(app):
    deadline=time.monotonic()+15
    while app.running and time.monotonic()<deadline:
        app.update()
        time.sleep(0.05)
    app.update()
    assert not app.running

def main():
    exe=ROOT/'.tools/pastel/pastel-v0.12.0-x86_64-pc-windows-msvc/pastel.exe'
    def run(value):
        return core.convert_color(exe,value,threading.Event())
    red=run('red')
    assert red=={'hex':'#ff0000','rgb':'rgb(255, 0, 0)','hsl':'hsl(0, 100.0%, 50.0%)'}
    assert run('#f00')==red
    assert run('hsl(0, 100%, 50%)')==red
    green=run('rgb(102, 187, 68)')
    assert green['hex']=='#66bb44'
    assert green==run('#66bb44')
    for bad in ['', '--help','rgba(1,2,3,0.5)','hsla(1,2%,3%,1)','#12345678','transparent','notacolor','red\nblue','x'*129]:
        try:
            run(bad)
        except ValueError:
            pass
        else:
            raise AssertionError('Invalid or transparent color accepted')
    original_popen=core.subprocess.Popen
    children=[]
    def slow_child(_cmd,**kwargs):
        child=original_popen([sys.executable,'-c','import time; time.sleep(30)'],**kwargs)
        children.append(child)
        return child
    core.subprocess.Popen=slow_child
    event=threading.Event()
    timer=threading.Timer(0.2,event.set)
    timer.start()
    try:
        core.convert_color(exe,'red',event)
    except InterruptedError:
        assert children and children[0].poll() is not None
    else:
        raise AssertionError('Stop ignored')
    finally:
        timer.cancel()
        core.subprocess.Popen=original_popen
    spec=importlib.util.spec_from_file_location('kiwi_color',HERE/'main.py')
    module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.resource_dir=lambda:exe.parent
    app=module.App()
    try:
        app.update()
        time.sleep(0.2)
        app.update()
        app.color.set('rgb(102, 187, 68)')
        app.start_convert()
        wait(app)
        assert app.hex_value.get()==green['hex'],app.status.get()
        assert app.rgb_value.get()==green['rgb']
        assert app.hsl_value.get()==green['hsl']
        assert app.preview.cget('background')=='#66bb44'
        app.copy_value('hex')
        assert app.clipboard_get()=='#66bb44'
        app.geometry('900x420+100+100')
        app.attributes('-topmost',True)
        app.update()
        app.lift()
        time.sleep(0.4)
        x,y=app.winfo_rootx(),app.winfo_rooty()
        ImageGrab.grab(bbox=(x,y,x+app.winfo_width(),y+app.winfo_height())).save(ROOT/'site/assets/screenshots/kiwi-color-public.png')
        app.color.set('red')
        assert app.hex_value.get()==''
        original_convert=module.convert_color
        def slow_convert(_exe,_color,event):
            assert event.wait(5)
            raise InterruptedError()
        module.convert_color=slow_convert
        app.start_convert()
        app.update()
        app.stop_convert()
        wait(app)
        assert '停止' in app.status.get()
        module.convert_color=original_convert
    finally:
        app.close()
    print('PASS: actual named/HEX/RGB/HSL colors, opacity validation, process stop, GUI preview, copy and stale-result clearing')

if __name__=='__main__':
    main()
