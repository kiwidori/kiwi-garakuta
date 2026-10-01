"""Verify actual grex generation on Windows and capture a public GUI image."""
from pathlib import Path
import importlib.util
import threading
import time
import tempfile
import shutil
import re
import sys
from PIL import ImageGrab

ROOT = Path(__file__).resolve().parents[2]

def wait(app):
    deadline = time.monotonic() + 20
    while app.running and time.monotonic() < deadline:
        app.update()
        time.sleep(0.05)
    app.update()
    assert not app.running, 'GUI timed out'

def main():
    spec = importlib.util.spec_from_file_location('kiwi_regex', Path(__file__).with_name('main.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    with tempfile.TemporaryDirectory(prefix='KiwiRegex-', dir='C:/Users/Public/Documents') as temp:
        folder = Path(temp) / '日本語フォルダー'
        folder.mkdir()
        exe = folder / 'grex.exe'
        shutil.copy2(ROOT / '.tools/grex/grex.exe', exe)
        def run(text, digits=False, ignore=False, repeats=False):
            return module.generate(exe, text, digits, ignore, repeats, threading.Event())
        pattern = run('りんご100\nりんご200\nみかん300')
        compiled = re.compile(pattern)
        assert all(compiled.fullmatch(t) for t in ['りんご100','りんご200','みかん300'])
        assert not compiled.fullmatch('ばなな100')
        assert not compiled.fullmatch('りんご999')
        assert re.fullmatch(run('注文123\n注文456', digits=True), '注文789')
        assert re.fullmatch(run('Kiwi', ignore=True), 'KIWI')
        assert re.fullmatch(run('abcabcabc', repeats=True), 'abcabcabc')
        assert re.fullmatch(run(' leading \n\ntrailing '), ' leading ')
        assert re.fullmatch(run('--help\n[abc].*'), '--help')
        assert module.validated_examples('a\r\nb\n') == ['a','b']
        assert module.validated_examples('a\u2028b') == ['a\u2028b']
        for invalid in ['', '\n\n', 'a\0b', 'a\rb', 'x'*257, '\n'.join(['a']*101), '\n'.join(['あ'*200]*30)]:
            try:
                module.validated_examples(invalid)
            except ValueError:
                pass
            else:
                raise AssertionError('Invalid input accepted')
        cancelled = threading.Event()
        cancelled.set()
        try:
            module.generate(exe, 'abc', False, False, False, cancelled)
        except InterruptedError:
            pass
        else:
            raise AssertionError('Cancellation ignored')
        # A deliberately slow child verifies real process termination on Stop.
        original_popen = module.subprocess.Popen
        children = []
        def slow_child(_cmd, **kwargs):
            child = original_popen([sys.executable, '-c', 'import time; time.sleep(30)'], **kwargs)
            children.append(child)
            return child
        module.subprocess.Popen = slow_child
        timed_cancel = threading.Event()
        timer = threading.Timer(0.2, timed_cancel.set)
        timer.start()
        started = time.monotonic()
        try:
            module.generate(exe, 'abc', False, False, False, timed_cancel)
        except InterruptedError:
            assert time.monotonic() - started < 2
            assert children and children[0].poll() is not None, 'Child survived cancellation'
        else:
            raise AssertionError('Running child cancellation failed')
        finally:
            module.subprocess.Popen = original_popen
            timer.cancel()
        module.resource_dir = lambda: folder
        app = module.App()
        try:
            app.examples.delete('1.0','end')
            app.examples.insert('1.0', '注文100\n注文200\n注文300')
            app.start_generate()
            wait(app)
            result = app.output.get('1.0','end-1c')
            assert re.fullmatch(result, '注文200'), app.status.get()
            app._copy_output()
            assert app.clipboard_get() == result
            app.geometry('900x620+100+100')
            app.attributes('-topmost', True)
            app.update()
            app.lift()
            time.sleep(0.5)
            x,y = app.winfo_rootx(), app.winfo_rooty()
            ImageGrab.grab(bbox=(x,y,x+app.winfo_width(),y+app.winfo_height())).save(ROOT/'site/assets/screenshots/kiwi-regex-public.png')
            original = module.generate
            def slow(_exe,_text,_digits,_case,_rep,event):
                assert event.wait(5), 'Stop failed'
                raise InterruptedError('生成を停止しました。')
            module.generate = slow
            app.start_generate()
            app.update()
            app.stop_generate()
            wait(app)
            assert '停止' in app.status.get()
            module.generate = original
        finally:
            app.close()
    print('PASS: actual grex, Japanese paths, literal/option matches, input bounds, GUI generation and stop')

if __name__ == '__main__':
    main()
