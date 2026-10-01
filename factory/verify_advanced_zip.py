"""Extract each portable ZIP and open its bundled advanced window via Win32 menu."""
import ast
import ctypes
import json
import subprocess
import tempfile
import time
import zipfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
user32=ctypes.windll.user32
user32.GetMenu.argtypes=[ctypes.c_void_p];user32.GetMenu.restype=ctypes.c_void_p
user32.GetSubMenu.argtypes=[ctypes.c_void_p,ctypes.c_int];user32.GetSubMenu.restype=ctypes.c_void_p
user32.GetMenuItemID.argtypes=[ctypes.c_void_p,ctypes.c_int];user32.GetMenuItemID.restype=ctypes.c_uint
user32.PostMessageW.argtypes=[ctypes.c_void_p,ctypes.c_uint,ctypes.c_size_t,ctypes.c_ssize_t]

def windows():
    found={}
    callback=ctypes.WINFUNCTYPE(ctypes.c_bool,ctypes.c_void_p,ctypes.c_void_p)
    def visitor(hwnd,_):
        length=user32.GetWindowTextLengthW(hwnd)
        if length:
            buffer=ctypes.create_unicode_buffer(length+1)
            user32.GetWindowTextW(hwnd,buffer,length+1)
            found[hwnd]=buffer.value
        return True
    user32.EnumWindows(callback(visitor),0)
    return found

def wait_window(title,existing):
    deadline=time.monotonic()+20
    while time.monotonic()<deadline:
        matches=[hwnd for hwnd,name in windows().items() if name==title and hwnd not in existing]
        if matches:return matches[0]
        time.sleep(.1)
    raise AssertionError('Window did not open: '+title)

def main():
    results=[]
    for app in sorted((ROOT/'apps').glob('kiwi-*')):
        package=next(app.glob('*-0.2.0-win11-x64.zip'))
        module=ast.parse((app/'main.py').read_text(encoding='utf8'))
        constants={n.targets[0].id:n.value.value for n in module.body if isinstance(n,ast.Assign) and isinstance(n.targets[0],ast.Name) and isinstance(n.value,ast.Constant)}
        title_arg=next(n.args[0] for n in ast.walk(module) if isinstance(n,ast.Call) and isinstance(n.func,ast.Attribute) and n.func.attr=='title' and n.args)
        title=title_arg.value if isinstance(title_arg,ast.Constant) else constants[title_arg.id]
        spec=json.loads((app/'advanced-spec.json').read_text(encoding='utf8'))
        with zipfile.ZipFile(package) as archive,tempfile.TemporaryDirectory(prefix='kiwi-advanced-zip-') as temp:
            names=archive.namelist()
            assert {'README.txt','LICENSE'}<=set(names)
            assert any('LICENSE' in n or 'COPYING' in n for n in names if n not in ('LICENSE','README.txt'))
            exe=next(n for n in names if n.endswith('.exe'))
            archive.extractall(temp)
            existing=windows()
            process=subprocess.Popen([str(Path(temp)/exe)])
            root=0
            try:
                root=wait_window(title,existing)
                menu=user32.GetMenu(root);assert menu,'advanced menu missing'
                submenu=user32.GetSubMenu(menu,0);assert submenu
                item=user32.GetMenuItemID(submenu,0);assert item!=0xffffffff
                user32.PostMessageW(root,0x0111,item,0)
                detail=wait_window(spec['tool']+' - 詳細機能',existing)
                assert detail
                user32.PostMessageW(detail,0x0010,0,0)
                time.sleep(.1)
                user32.PostMessageW(root,0x0010,0,0)
                process.wait(timeout=10);assert process.returncode==0
            finally:
                if process.poll() is None:
                    subprocess.run(['taskkill','/F','/T','/PID',str(process.pid)],capture_output=True)
                    process.wait(timeout=10)
        results.append({'slug':app.name,'zip':package.name,'passed':True})
        print('PASS:',app.name,'extracted ZIP licenses, normal GUI, advanced GUI and close',flush=True)
    target=ROOT/'data/feature-audit/zip-results.json'
    target.write_text(json.dumps(results,indent=2),encoding='utf8')

if __name__=='__main__':main()
