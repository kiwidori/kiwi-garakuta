"""Exercise real yq conversion and capture a public Windows screenshot."""
import sys
import json
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

def wait(app):
    deadline=time.monotonic()+15
    while app.running and time.monotonic()<deadline:
        app.update()
        time.sleep(0.05)
    app.update()
    assert not app.running,'GUI did not finish'

def main():
    exe=ROOT/'.tools/yq/yq_windows_amd64.exe'
    with tempfile.TemporaryDirectory(prefix='KiwiYAML-',dir='C:/Users/Public/Documents') as temp:
        folder=Path(temp)
        source=folder/'日本語設定.yaml'
        source.write_text('name: きうい\nports: [8080, 8081]\nenabled: true\nnote: サンプル設定\n',encoding='utf-8')
        original=source.read_bytes()
        result=core.convert(exe,source,'json',threading.Event())
        obj=json.loads(result)
        assert obj['name']=='きうい' and obj['ports']==[8080,8081] and obj['enabled'] is True
        assert obj['note']=='サンプル設定'
        literal=folder/'文字列.yml'
        literal.write_text('value: "env(TEST) load(example.txt)"\n',encoding='utf-8')
        assert json.loads(core.convert(exe,literal,'json',threading.Event()))['value']=='env(TEST) load(example.txt)'
        assert source.read_bytes()==original
        formatted=core.convert(exe,source,'yaml',threading.Event())
        assert '  - 8080' in formatted and 'name: きうい' in formatted
        multiple=folder/'複数.yml'
        multiple.write_text('name: first\n---\nname: second\n',encoding='utf-8')
        stream=core.convert(exe,multiple,'json',threading.Event()).strip()
        decoder=json.JSONDecoder()
        doc1,end=decoder.raw_decode(stream)
        doc2=json.loads(stream[end:].strip())
        assert doc1['name']=='first' and doc2['name']=='second'
        bad=folder/'不正.yaml'
        bad.write_text('name: [unterminated',encoding='utf-8')
        for input_path in [bad,folder/'不存在.yml']:
            try:
                core.convert(exe,input_path,'json',threading.Event())
            except ValueError:
                pass
            else:
                raise AssertionError('Invalid YAML accepted')
        oversized=folder/'大きすぎる.yml'
        oversized.write_bytes(b'x'*(core.MAX_INPUT+1))
        try:
            core.convert(exe,oversized,'yaml',threading.Event())
        except ValueError:
            pass
        else:
            raise AssertionError('Oversized input accepted')
        saved=folder/'保存.json'
        core.save_result(result,source,saved)
        assert json.loads(saved.read_text(encoding='utf-8'))==obj
        for target in [source,saved]:
            try:
                core.save_result(result,source,target)
            except ValueError:
                pass
            else:
                raise AssertionError('Overwrite accepted')
        cancelled=threading.Event()
        cancelled.set()
        try:
            core.convert(exe,source,'yaml',cancelled)
        except InterruptedError:
            pass
        else:
            raise AssertionError('Cancelled run accepted')
        spec=importlib.util.spec_from_file_location('kiwi_yaml',HERE/'main.py')
        module=importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        module.resource_dir=lambda:exe.parent
        # Source tests use official exe name; packaged app embeds it as yq.exe.
        module_exe=exe.parent/'yq.exe'
        if not module_exe.exists():
            module_exe.write_bytes(exe.read_bytes())
        app=module.App()
        try:
            app.update()
            time.sleep(0.2)
            app.update()
            app.source.set(str(source))
            app.mode.set('JSON変換')
            app.start_convert()
            wait(app)
            assert json.loads(app.result_text)==obj,app.status.get()
            app.save_to(folder/'GUI保存.json')
            assert json.loads((folder/'GUI保存.json').read_text(encoding='utf-8'))==obj
            app.geometry('980x620+100+100')
            app.attributes('-topmost',True)
            app.update()
            app.lift()
            time.sleep(0.4)
            x,y=app.winfo_rootx(),app.winfo_rooty()
            ImageGrab.grab(bbox=(x,y,x+app.winfo_width(),y+app.winfo_height())).save(ROOT/'site/assets/screenshots/kiwi-yaml-public.png')
            original_convert=module.convert
            def slow(_exe,_src,_mode,event):
                assert event.wait(5)
                raise InterruptedError()
            module.convert=slow
            app.start_convert()
            app.update()
            app.stop_convert()
            wait(app)
            assert '停止' in app.status.get()
            module.convert=original_convert
        finally:
            app.close()
    print('PASS: actual yq YAML/JSON, Unicode, multiple documents, source unchanged, invalid/large input, save protection and GUI stop')

if __name__=='__main__':
    main()
