"""Build the portable structured data workspace from pinned upstream assets."""
import hashlib,io,json,os,shutil,subprocess,sys,tempfile,zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT.parent/'common'))
from portable_build import fetch

def build():
    if os.name!='nt':raise SystemExit('Build on Windows.')
    import tkinter
    if tkinter.Tcl().call('info','patchlevel')!='8.6.15':raise ValueError('Tcl runtime version mismatch')
    tcl_license=ROOT.parent/'common/tcl-8.6.15-LICENSE.terms'
    if hashlib.sha256(tcl_license.read_bytes()).hexdigest()!='c0a69a2bfd757361ec7e6143973b103c90409316b49e9c88db26ad6388e79f16':raise ValueError('Tcl license digest mismatch')
    pins=json.loads((ROOT/'upstream-pins.json').read_text(encoding='utf8'))
    assert set(pins)=={'fx','gojq','gron'}
    licenses=[]
    with tempfile.TemporaryDirectory(prefix='kiwi-json-workbench-') as td:
        folder=Path(td)
        cmd=[sys.executable,'-m','PyInstaller','--noconfirm','--clean','--onefile','--noconsole','--paths',str(ROOT.parent/'common'),'--name','KiwiJsonWorkbench','--distpath',str(folder/'dist'),'--workpath',str(folder/'build'),'--specpath',str(folder)]
        for engine,pin in pins.items():
            data=fetch(pin['url'],pin['sha']);lic=fetch(pin['license_url'],pin['license_sha'])
            binary=zipfile.ZipFile(io.BytesIO(data)).read(pin.get('archive_member',pin['exe'])) if pin['asset'].endswith('.zip') else data
            if hashlib.sha256(binary).hexdigest()!=pin['binary_sha']:raise ValueError('Bundled native digest mismatch: '+engine)
            exe=folder/pin['exe'];exe.write_bytes(binary);cmd+=['--add-binary',str(exe)+os.pathsep+'.']
            licenses.append('=== '+pin['repo']+' '+pin['tag']+' ===\nSource: '+pin['license_url']+'\n'+lic.decode('utf8'))
        cmd+=['--add-data',str(ROOT/'profiles')+os.pathsep+'profiles']
        subprocess.run([*cmd,str(ROOT/'main.py')],check=True)
        release=ROOT/'release'
        if release.is_symlink() or release.is_junction() or release.resolve().parent!=ROOT:raise ValueError('Unsafe release directory')
        if release.exists():shutil.rmtree(release)
        release.mkdir();shutil.copy2(folder/'dist/KiwiJsonWorkbench.exe',release/'KiwiJsonWorkbench.exe')
        (release/'UPSTREAM-LICENSE.txt').write_text('\n\n'.join(licenses),encoding='utf8')
        for name in ('README.txt','THIRD-PARTY-NOTICES.txt'):shutil.copy2(ROOT/name,release/name)
        shutil.copy2(ROOT.parents[1]/'LICENSE',release/'LICENSE');shutil.copy2(ROOT/'upstream-pins.json',release/'UPSTREAM-PINS.json')
        runtime_notices=[]
        for title,path in [('Python',Path(sys.base_prefix)/'LICENSE.txt'),('Tcl8.6.15',tcl_license),('Tk',Path(sys.base_prefix)/'tcl/tk8.6/license.terms')]:
            if not path.is_file():raise ValueError('Missing runtime license: '+title)
            runtime_notices.append('=== '+title+' ===\n'+path.read_text(encoding='utf8'))
        (release/'Runtime-LICENSES.txt').write_text('\n\n'.join(runtime_notices),encoding='utf8')
    package=ROOT/'KiwiJsonWorkbench-0.1.0-win11-x64.zip'
    with zipfile.ZipFile(package,'w',zipfile.ZIP_DEFLATED,compresslevel=9) as z:
        for path in sorted(release.iterdir()):z.write(path,path.name)
    print('Built',package.name,package.stat().st_size,'SHA256',hashlib.sha256(package.read_bytes()).hexdigest())
if __name__=='__main__':build()
