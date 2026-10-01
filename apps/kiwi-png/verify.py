"""Real lossless PNG tests and a public Windows GUI screenshot."""
from pathlib import Path
import sys
import tempfile
import threading
import importlib.util
import time
import struct
import zlib
from PIL import Image,ImageGrab
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
    exe=ROOT/'.tools/oxipng/oxipng-10.2.1-x86_64-pc-windows-msvc/oxipng.exe'
    with tempfile.TemporaryDirectory(prefix='KiwiPNG-',dir='C:/Users/Public/Documents') as temp:
        folder=Path(temp)
        source=folder/'日本語サンプル.png'
        output=folder/'圧縮済み.png'
        # Synthetic pixels, including transparent pixels with nonzero RGB.
        image=Image.new('RGBA',(240,120))
        image.putdata([(x%16*16,y%8*32,80,0 if x<40 else 255) for y in range(120) for x in range(240)])
        image.save(source,compress_level=0)
        before=source.read_bytes()
        result=core.optimize(exe,source,output,2,threading.Event())
        assert source.read_bytes()==before
        assert result['after']<result['before']
        with Image.open(output) as optimized:
            assert optimized.convert('RGBA').tobytes()==image.tobytes(),'Pixels changed'
        for destination in [source,output]:
            try:
                core.optimize(exe,source,destination,2,threading.Event())
            except ValueError:
                pass
            else:
                raise AssertionError('Overwrite accepted')
        bad=folder/'invalid.png'
        bad.write_bytes(b'not a PNG')
        try:
            core.optimize(exe,bad,folder/'invalid-output.png',2,threading.Event())
        except ValueError:
            assert not (folder/'invalid-output.png').exists()
        else:
            raise AssertionError('Invalid PNG accepted')
        chunk_data=struct.pack('>II',1,0)
        chunk=b'acTL'+chunk_data
        animated=before[:33]+struct.pack('>I',8)+chunk+struct.pack('>I',zlib.crc32(chunk))+before[33:]
        try:
            core.validate_png(animated)
        except ValueError:
            pass
        else:
            raise AssertionError('APNG accepted')
        event=threading.Event()
        event.set()
        try:
            core.optimize(exe,source,folder/'cancelled.png',2,event)
        except InterruptedError:
            assert not (folder/'cancelled.png').exists()
        else:
            raise AssertionError('Cancel ignored')
        spec=importlib.util.spec_from_file_location('kiwi_png',HERE/'main.py')
        module=importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        module.resource_dir=lambda:exe.parent
        app=module.App()
        try:
            app.source.set(str(source))
            app.destination.set(str(folder/'GUI圧縮済み.png'))
            app.start_optimize()
            wait(app)
            assert (folder/'GUI圧縮済み.png').exists(),app.status.get()
            app.geometry('900x420+100+100')
            app.attributes('-topmost',True)
            app.update()
            app.lift()
            time.sleep(0.4)
            x,y=app.winfo_rootx(),app.winfo_rooty()
            ImageGrab.grab(bbox=(x,y,x+app.winfo_width(),y+app.winfo_height())).save(ROOT/'site/assets/screenshots/kiwi-png-public.png')
            original=module.optimize
            def slow(_exe,_src,_dest,_level,cancel):
                assert cancel.wait(5)
                raise InterruptedError()
            module.optimize=slow
            app.destination.set(str(folder/'GUI停止.png'))
            app.start_optimize()
            app.update()
            app.stop_optimize()
            wait(app)
            assert '停止' in app.status.get()
            assert not (folder/'GUI停止.png').exists()
            module.optimize=original
        finally:
            app.close()
    print('PASS: actual PNG size reduction, RGBA pixel equality, unchanged original, no overwrite, Unicode paths, APNG rejection, GUI stop')

if __name__=='__main__':
    main()
