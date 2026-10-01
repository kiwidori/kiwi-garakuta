"""Verify actual Windows conversion, cancellation and public GUI screenshot."""
import importlib.util
import hashlib
import sys
import threading
import time
from pathlib import Path
from PIL import Image,ImageDraw,ImageGrab
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
sys.path.insert(0,str(HERE))
import core

def wait(app):
    deadline=time.monotonic()+35
    while app.running and time.monotonic()<deadline:
        app.update()
        time.sleep(0.05)
    app.update()
    assert not app.running

def main():
    folder=Path('C:/Users/Public/Documents/kiwi-ascii-demo')
    folder.mkdir(exist_ok=True)
    path=folder/'文字絵サンプル.png'
    image=Image.new('RGB',(320,200),'white')
    draw=ImageDraw.Draw(image)
    draw.ellipse((65,30,220,180),fill='black')
    draw.ellipse((175,15,255,95),fill='black')
    draw.polygon([(247,40),(300,60),(246,75)],fill='black')
    draw.ellipse((222,37,231,46),fill='white')
    draw.line((110,170,105,194),fill='black',width=7)
    draw.line((170,175,178,194),fill='black',width=7)
    image.save(path)
    before=hashlib.sha256(path.read_bytes()).hexdigest()
    exe=ROOT/'.tools/ascii/ascii-image-converter_Windows_amd64_64bit/ascii-image-converter.exe'
    def run(p=path,width=80,negative=False,braille=False):
        return core.convert_image(exe,p,width,negative,braille,threading.Event())
    normal=run()
    assert normal.strip() and '\x1b' not in normal
    assert max(map(len,normal.splitlines()))==80
    assert run(negative=True)!=normal
    for suffix in ('jpg','bmp','webp','tiff'):
        other=folder/('sample.'+suffix)
        image.save(other)
        assert run(other).strip()
    dots=run(braille=True)
    assert any(0x2800<=ord(c)<=0x28ff for c in dots)
    # Controlled half-black/half-white input must retain contrast.
    split=folder/'contrast.png'
    sample=Image.new('RGB',(100,100),'white')
    ImageDraw.Draw(sample).rectangle((0,0,49,99),fill='black')
    sample.save(split)
    lines=run(split,40).splitlines()
    assert lines and all(len(line)==40 for line in lines)
    assert not lines[0][:15].strip() and lines[0][-15:].strip()
    assert hashlib.sha256(path.read_bytes()).hexdigest()==before
    broken=folder/'壊れた.png'
    broken.write_bytes(b'not an image')
    bad=[(broken,80),(folder/'missing.png',80),(path,19),(path,161),(Path('https://example.com/a.png'),80)]
    animation=folder/'animation.webp'
    image.save(animation,save_all=True,append_images=[Image.new('RGB',image.size,'black')],duration=100,loop=0)
    bad.append((animation,80))
    for p,width in bad:
        try:
            run(p,width)
        except ValueError:
            pass
        else:
            raise AssertionError('Invalid input accepted')
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
        core.convert_image(exe,path,80,False,False,event)
    except InterruptedError:
        assert children and children[0].poll() is not None
    else:
        raise AssertionError('Cancellation ignored')
    finally:
        timer.cancel()
        core.subprocess.Popen=original
    spec=importlib.util.spec_from_file_location('kiwi_ascii',HERE/'main.py')
    module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.resource_dir=lambda:exe.parent
    app=module.App()
    try:
        app.update()
        time.sleep(0.2)
        app.update()
        app.path.set(str(path))
        app.width.set('80')
        app.start_convert()
        wait(app)
        assert app.output.get('1.0','end-1c')==normal,app.status.get()
        app.copy_output()
        assert app.clipboard_get()==normal
        destination=folder/'result.txt'
        module.filedialog.asksaveasfilename=lambda **kwargs:str(destination)
        app.save_output()
        assert destination.read_bytes()==normal.encode('utf-8')
        module.filedialog.asksaveasfilename=lambda **kwargs:str(path)
        app.save_output()
        assert hashlib.sha256(path.read_bytes()).hexdigest()==before
        app.status.set('変換完了')
        app.geometry('1000x720+100+100')
        app.attributes('-topmost',True)
        app.update()
        app.lift()
        time.sleep(0.3)
        x,y=app.winfo_rootx(),app.winfo_rooty()
        ImageGrab.grab(bbox=(x,y,x+app.winfo_width(),y+app.winfo_height())).save(ROOT/'site/assets/screenshots/kiwi-ascii-public.png')
        app.negative.set(True)
        assert not app.output.get('1.0','end-1c')
        def slow_convert(_exe,_path,_width,_negative,_braille,event):
            assert event.wait(5)
            raise InterruptedError()
        module.convert_image=slow_convert
        app.start_convert()
        app.update()
        app.stop_convert()
        wait(app)
        assert '停止' in app.status.get()
    finally:
        app.close()
    print('PASS: real Unicode-path conversion, width, contrast, inversion, braille, invalid/animated input, process stop, GUI, UTF8 save and original preservation')

if __name__=='__main__':
    main()
