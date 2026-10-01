"""Verify b3sum with official BLAKE3 vectors and a Windows GUI."""
import sys
import time
import tempfile
import threading
import importlib.util
from pathlib import Path
from PIL import ImageGrab
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
sys.path.insert(0,str(HERE))
import core
# https://github.com/BLAKE3-team/BLAKE3/blob/1.8.7/test_vectors/test_vectors.json
EMPTY='af1349b9f5f9a1a6a0404dea36dcc9499bcb25c9adc112b7cc9a93cae41f3262'
PATTERN1024='42214739f095a406f3fc83deb889744ac00df831c10daa55189b5d121c855af7'

def wait(app):
    deadline=time.monotonic()+15
    while app.running and time.monotonic()<deadline:
        app.update()
        time.sleep(0.05)
    app.update()
    assert not app.running

def main():
    exe=ROOT/'.tools/b3sum_windows_x64_bin.exe'
    with tempfile.TemporaryDirectory(prefix='KiwiHash-',dir='C:/Users/Public/Documents') as temp:
        folder=Path(temp)
        empty=folder/'空のファイル.txt'
        empty.write_bytes(b'')
        source=folder/'日本語サンプル.bin'
        original=bytes(i%251 for i in range(1024))
        source.write_bytes(original)
        assert core.hash_file(exe,empty,threading.Event())==EMPTY
        assert core.hash_file(exe,source,threading.Event())==PATTERN1024
        assert source.read_bytes()==original
        assert core.normalize_expected(' '+PATTERN1024.upper()+' ')==PATTERN1024
        assert core.normalize_expected('')==''
        for text in ['g'*64,'0'*63]:
            try:
                core.normalize_expected(text)
            except ValueError:
                pass
            else:
                raise AssertionError('Invalid comparison accepted')
        try:
            core.hash_file(exe,folder/'missing',threading.Event())
        except ValueError:
            pass
        else:
            raise AssertionError('Missing input accepted')
        original_popen=core.subprocess.Popen
        children=[]
        def slow_child(_cmd,**kwargs):
            child=original_popen([sys.executable,'-c','import time; time.sleep(30)'],**kwargs)
            children.append(child)
            return child
        core.subprocess.Popen=slow_child
        cancel=threading.Event()
        timer=threading.Timer(0.2,cancel.set)
        timer.start()
        try:
            core.hash_file(exe,source,cancel)
        except InterruptedError:
            assert children[0].poll() is not None,'Child survived Stop'
        else:
            raise AssertionError('Stop ignored')
        finally:
            timer.cancel()
            core.subprocess.Popen=original_popen
        changed=folder/'更新試験.bin'
        changed.write_bytes(b'before')
        def mutating_child(_cmd,**kwargs):
            return original_popen([sys.executable,'-c',"import sys,pathlib; pathlib.Path(sys.argv[1]).write_bytes(b'after-change');print('0'*64)",str(changed)],**kwargs)
        core.subprocess.Popen=mutating_child
        try:
            core.hash_file(exe,changed,threading.Event())
        except ValueError as error:
            assert '変更' in str(error)
        else:
            raise AssertionError('Changed input accepted')
        finally:
            core.subprocess.Popen=original_popen
        spec=importlib.util.spec_from_file_location('kiwi_hash',HERE/'main.py')
        module=importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        packaged_name=exe.parent/'b3sum.exe'
        if not packaged_name.exists():
            packaged_name.write_bytes(exe.read_bytes())
        module.resource_dir=lambda:exe.parent
        app=module.App()
        try:
            app.update()
            time.sleep(0.2)
            app.update()
            app.source.set(str(source))
            app.expected.set('0'*64)
            app.start_hash()
            wait(app)
            assert '不一致' in app.status.get(),app.status.get()
            app.expected.set(PATTERN1024.upper())
            app.start_hash()
            wait(app)
            assert app.digest.get()==PATTERN1024
            assert '一致' in app.status.get() and '不一致' not in app.status.get()
            app.copy_hash()
            assert app.clipboard_get()==PATTERN1024
            app.geometry('900x360+100+100')
            app.attributes('-topmost',True)
            app.update()
            app.lift()
            time.sleep(0.4)
            x,y=app.winfo_rootx(),app.winfo_rooty()
            ImageGrab.grab(bbox=(x,y,x+app.winfo_width(),y+app.winfo_height())).save(ROOT/'site/assets/screenshots/kiwi-hash-public.png')
            original_hash=module.hash_file
            def slow_hash(_exe,_src,event):
                assert event.wait(5)
                raise InterruptedError()
            module.hash_file=slow_hash
            app.start_hash()
            app.update()
            app.stop_hash()
            wait(app)
            assert '停止' in app.status.get()
            module.hash_file=original_hash
        finally:
            app.close()
    print('PASS: official vectors, Unicode paths, unchanged file, comparison, changed-file rejection, real process stop, GUI copy')

if __name__=='__main__':
    main()
