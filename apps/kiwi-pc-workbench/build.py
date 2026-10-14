"""Build a portable Windows application from pinned official assets."""
import hashlib,io,json,os,shutil,subprocess,sys,tempfile,zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT.parent/'common'))
from portable_build import fetch

def build():
    if os.name!='nt':raise SystemExit('Build on Windows 11 x64.')
    import tkinter
    if tkinter.Tcl().call('info','patchlevel')!='8.6.15':raise ValueError('Tcl version mismatch')
    tcl=ROOT.parent/'common/tcl-8.6.15-LICENSE.terms'
    if hashlib.sha256(tcl.read_bytes()).hexdigest()!='c0a69a2bfd757361ec7e6143973b103c90409316b49e9c88db26ad6388e79f16':raise ValueError('Tcl license mismatch')
    pins=json.loads((ROOT/'upstream-pins.json').read_text(encoding='utf8'))
    if set(pins)!={'dust','duf','fastfetch'}:raise ValueError('Native manifest mismatch')
    with tempfile.TemporaryDirectory(prefix='kiwi-pc-workbench-build-') as td:
        folder=Path(td)
        cmd=[sys.executable,'-m','PyInstaller','--noconfirm','--clean','--onefile','--noconsole','--paths',str(ROOT.parent/'common'),'--name','KiwiPcWorkbench','--distpath',str(folder/'dist'),'--workpath',str(folder/'build'),'--specpath',str(folder)]
        for e,p in pins.items():
            cache=ROOT.parents[1]/'data/pc-workbench' if os.environ.get('KIWI_USE_NATIVE_CACHE')=='1' else None
            if cache:
                binary=(cache/p['exe']).read_bytes();z=None
            else:
                raw=fetch(p['url'],p['sha']);z=zipfile.ZipFile(io.BytesIO(raw)) if p['kind']=='zip' else None
                binary=z.read(p['archive_member']) if z else raw
            if hashlib.sha256(binary).hexdigest()!=p['binary_sha']:raise ValueError('Native digest mismatch')
            exe=folder/p['exe'];exe.write_bytes(binary);cmd+=['--add-binary',str(exe)+os.pathsep+'.']
            if 'license_url' in p:
                license_data=(ROOT/p['license_file']).read_bytes()
                if hashlib.sha256(license_data).hexdigest()!=p['license_sha']:raise ValueError('License digest mismatch')
                if not cache and fetch(p['license_url'],p['license_sha'])!=license_data:raise ValueError('License mismatch')
            else:
                body=(ROOT/p['license_file']).read_bytes()
                if hashlib.sha256(body).hexdigest()!=p['local_license_sha']:raise ValueError('Native license digest mismatch')
                if not cache and z.read(p['license_members'][0])!=body:raise ValueError('Native license mismatch')
        cmd+=['--add-data',str(ROOT/'profiles')+os.pathsep+'profiles',str(ROOT/'main.py')]
        for n in ('advanced-spec.json','upstream-help.txt'):cmd[-1:-1]=['--add-data',str(ROOT/n)+os.pathsep+'.']
        subprocess.run(cmd,check=True)
        release=ROOT/'release'
        if release.is_symlink() or release.is_junction() or release.resolve().parent!=ROOT:raise ValueError('Unsafe release directory')
        if release.exists():shutil.rmtree(release)
        release.mkdir();shutil.copy2(folder/'dist/KiwiPcWorkbench.exe',release)
        for n in ('README.txt','THIRD-PARTY-NOTICES.txt','PyInstaller-LICENSE.txt','OpenSSL-LICENSE.txt','upstream-pins.json','dust-LICENSE','duf-LICENSE','fastfetch-LICENSE'):shutil.copy2(ROOT/n,release/n)
        shutil.copy2(ROOT.parents[1]/'LICENSE',release/'LICENSE')
        texts=[]
        for n,p in [('Python',Path(sys.base_prefix)/'LICENSE.txt'),('Tcl8.6.15',tcl),('Tk',Path(sys.base_prefix)/'tcl/tk8.6/license.terms')]:texts.append('=== '+n+' ===\n'+p.read_text(encoding='utf8'))
        (release/'Runtime-LICENSES.txt').write_text('\n\n'.join(texts),encoding='utf8')
    output=ROOT/'KiwiPcWorkbench-0.1.0-win11-x64.zip'
    with zipfile.ZipFile(output,'w',zipfile.ZIP_DEFLATED,compresslevel=9) as z:
        for p in sorted(release.iterdir()):z.write(p,p.name)
    print('Built',output.name,output.stat().st_size,'SHA256',hashlib.sha256(output.read_bytes()).hexdigest())
if __name__=='__main__':build()
