"""Open the extracted portable Windows binaries and their advanced windows."""
import json
import hashlib
from pathlib import Path
import subprocess
import tempfile
import time
import zipfile
from verify_advanced_zip import windows, wait_window, user32
from PyInstaller.archive.readers import CArchiveReader

ROOT=Path(__file__).resolve().parents[1]


def main():
    results=[]
    for slug in ('kiwi-count','kiwi-shell','kiwi-minify'):
        app=ROOT/'apps'/slug
        pin=json.loads((app/'upstream-pin.json').read_text(encoding='utf8'))
        profile=json.loads((app/'profile.json').read_text(encoding='utf8'))
        package=app/f"{pin['app_exe']}-{pin['version']}-win11-x64.zip"
        with zipfile.ZipFile(package) as archive, tempfile.TemporaryDirectory(prefix='kiwi-three-zip-') as folder:
            assert {'README.txt','LICENSE','UPSTREAM-LICENSE.txt','THIRD-PARTY-NOTICES.txt','Runtime-LICENSES.txt'}<=set(archive.namelist())
            assert archive.read('THIRD-PARTY-NOTICES.txt').startswith(b'=== Go runtime')
            archive.extractall(folder)
            embedded=CArchiveReader(str(Path(folder)/f"{pin['app_exe']}.exe"))
            assert json.loads(embedded.extract('profile.json'))==profile,'frozen profile differs from source'
            assert hashlib.sha256(embedded.extract(pin['exe'])).digest()==hashlib.sha256((ROOT/'.tools'/slug/pin['exe']).read_bytes()).digest(),'upstream binary mismatch'
            modules=embedded.open_embedded_archive('PYZ.pyz').toc
            assert {'workbench_jobs','runtime','workbench'}<=set(modules),'worker modules missing from frozen executable'
            existing=windows();proc=subprocess.Popen([str(Path(folder)/f"{pin['app_exe']}.exe")])
            try:
                root=wait_window(profile['title'],existing)
                menu=user32.GetMenu(root);assert menu
                submenu=user32.GetSubMenu(menu,0);assert submenu
                item=user32.GetMenuItemID(submenu,0);assert item!=0xffffffff
                user32.PostMessageW(root,0x0111,item,0)
                detail=wait_window(profile['tool']+' - 詳細機能',existing)
                user32.PostMessageW(detail,0x0010,0,0);time.sleep(.15)
                user32.PostMessageW(root,0x0010,0,0)
                proc.wait(timeout=12);assert proc.returncode==0
            finally:
                if proc.poll() is None:
                    subprocess.run(['taskkill','/F','/T','/PID',str(proc.pid)],capture_output=True)
                    proc.wait(timeout=12)
        results.append({'slug':slug,'zip':package.name,'passed':True})
        print('PASS:',slug,'ZIP extraction, licenses, frozen native and advanced GUI, close',flush=True)
    (ROOT/'data/batch3/zip-results.json').write_text(json.dumps(results,indent=2),encoding='utf8')


if __name__=='__main__':main()
