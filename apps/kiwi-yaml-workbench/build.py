"""Build the YAML workspace from pinned native releases and a Windows Python wheel."""
import hashlib,io,json,os,shutil,subprocess,sys,tempfile,zipfile,tarfile
from pathlib import Path
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT.parent/'common'))
from portable_build import fetch

def build():
    if os.name!='nt':raise SystemExit('Build on Windows 11 x64 with Python 3.13.')
    import tkinter
    if tkinter.Tcl().call('info','patchlevel')!='8.6.15':raise ValueError('Tcl version mismatch')
    pins=json.loads((ROOT/'upstream-pins.json').read_text(encoding='utf8'))
    wheel_pin=json.loads((ROOT/'python-pin.json').read_text(encoding='utf8'))
    with tempfile.TemporaryDirectory(prefix='kiwi-yaml-workbench-build-') as td:
        folder=Path(td);vendor=folder/'vendor';vendor.mkdir()
        wheel=zipfile.ZipFile(io.BytesIO(fetch(wheel_pin['url'],wheel_pin['sha256'])))
        for name in wheel.namelist():
            if not (vendor/name).resolve().is_relative_to(vendor):raise ValueError('Invalid wheel path')
        wheel.extractall(vendor)
        cmd=[sys.executable,'-m','PyInstaller','--noconfirm','--clean','--onefile','--noconsole','--paths',str(vendor),'--paths',str(ROOT.parent/'common'),'--name','KiwiYamlWorkbench','--distpath',str(folder/'dist'),'--workpath',str(folder/'build'),'--specpath',str(folder)]
        for engine,pin in pins.items():
            raw=fetch(pin['url'],pin['sha'])
            if pin['kind']=='zip':binary=zipfile.ZipFile(io.BytesIO(raw)).read(pin['archive_member'])
            elif pin['kind']=='tar':
                with tarfile.open(fileobj=io.BytesIO(raw),mode='r:gz') as t:binary=t.extractfile(pin['archive_member']).read()
            elif pin['kind']=='exe':binary=raw
            else:raise ValueError('Unknown native asset type')
            if hashlib.sha256(binary).hexdigest()!=pin['binary_sha']:raise ValueError('Native digest mismatch')
            exe=folder/pin['exe'];exe.write_bytes(binary);cmd+=['--add-binary',str(exe)+os.pathsep+'.']
            if fetch(pin['license_url'],pin['license_sha'])!=(ROOT/pin['license_file']).read_bytes():raise ValueError('License mismatch')
        cmd+=['--add-data',str(ROOT/'profiles')+os.pathsep+'profiles',str(ROOT/'main.py')]
        subprocess.run(cmd,check=True,env={**os.environ,'PYTHONPATH':str(vendor)})
        release=ROOT/'release'
        if release.is_symlink() or release.is_junction() or release.resolve().parent!=ROOT:raise ValueError('Unsafe release directory')
        if release.exists():shutil.rmtree(release)
        release.mkdir();shutil.copy2(folder/'dist/KiwiYamlWorkbench.exe',release/'KiwiYamlWorkbench.exe')
        for name in ('README.txt','THIRD-PARTY-NOTICES.txt','PyInstaller-LICENSE.txt','upstream-pins.json','python-pin.json',*(p['license_file'] for p in pins.values())):shutil.copy2(ROOT/name,release/name)
        shutil.copy2(ROOT.parents[1]/'LICENSE',release/'LICENSE')
        tcl=ROOT.parent/'common/tcl-8.6.15-LICENSE.terms'
        if hashlib.sha256(tcl.read_bytes()).hexdigest()!='c0a69a2bfd757361ec7e6143973b103c90409316b49e9c88db26ad6388e79f16':raise ValueError('Tcl license mismatch')
        texts=[]
        for name,path in [('Python',Path(sys.base_prefix)/'LICENSE.txt'),('Tcl8.6.15',tcl),('Tk',Path(sys.base_prefix)/'tcl/tk8.6/license.terms')]:texts.append('=== '+name+' ===\n'+path.read_text(encoding='utf8'))
        (release/'Runtime-LICENSES.txt').write_text('\n\n'.join(texts),encoding='utf8')
    output=ROOT/'KiwiYamlWorkbench-0.1.1-win11-x64.zip'
    with zipfile.ZipFile(output,'w',zipfile.ZIP_DEFLATED,compresslevel=9) as archive:
        for p in sorted(release.iterdir()):archive.write(p,p.name)
    print('Built',output.name,output.stat().st_size,'SHA256',hashlib.sha256(output.read_bytes()).hexdigest())
if __name__=='__main__':build()
