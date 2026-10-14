"""Build the Windows portable application from the official pinned release."""
import hashlib,importlib.metadata,io,json,os,shutil,subprocess,sys,tempfile,zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT.parent/'common'))
from portable_build import fetch

def build():
    if os.name!='nt':raise SystemExit('Build on Windows x64.')
    import tkinter
    if tkinter.Tcl().call('info','patchlevel')!='8.6.15':raise ValueError('Tcl license version mismatch')
    pins=json.loads((ROOT/'upstream-pin.json').read_text(encoding='utf8'))
    cache=ROOT.parents[1]/'data/image-enlarge/realesrgan-ncnn-vulkan-20220424-windows.zip'
    raw=cache.read_bytes() if os.environ.get('KIWI_USE_NATIVE_CACHE')=='1' else fetch(pins['url'],pins['sha256'])
    if hashlib.sha256(raw).hexdigest()!=pins['sha256']:raise ValueError('Archive digest mismatch')
    for name,p in pins['licenses'].items():
        if hashlib.sha256((ROOT/name).read_bytes()).hexdigest()!=p['sha256']:raise ValueError('License digest mismatch: '+name)
    with tempfile.TemporaryDirectory(prefix='kiwi-image-build-') as td:
        folder=Path(td);native=folder/'native';native.mkdir()
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            for name,digest in pins['members'].items():
                if name not in ('realesrgan-ncnn-vulkan.exe',) and not name.startswith('models/'):raise ValueError('Unexpected native member')
                body=archive.read(name)
                if hashlib.sha256(body).hexdigest()!=digest:raise ValueError('Native digest mismatch')
                dest=native/name;dest.parent.mkdir(exist_ok=True);dest.write_bytes(body)
        payload=folder/'native-payload.zip'
        with zipfile.ZipFile(payload,'w',zipfile.ZIP_STORED) as z:
            for name in pins['members']:z.write(native/name,name)
        cmd=[sys.executable,'-m','PyInstaller','--noconfirm','--clean','--onefile','--noconsole','--paths',str(ROOT.parent/'common'),'--name','KiwiImageEnlarge','--distpath',str(folder/'dist'),'--workpath',str(folder/'build'),'--specpath',str(folder),'--add-data',str(payload)+os.pathsep+'.','--add-data',str(ROOT/'upstream-pin.json')+os.pathsep+'.','--add-data',str(ROOT/'upstream-help.txt')+os.pathsep+'.']
        for mod in ('numpy','matplotlib','IPython','olefile'):cmd+=['--exclude-module',mod]
        subprocess.run([*cmd,str(ROOT/'main.py')],check=True)
        release=ROOT/'release'
        if release.is_symlink() or release.is_junction() or release.resolve().parent!=ROOT:raise ValueError('Unsafe release directory')
        if release.exists():shutil.rmtree(release)
        release.mkdir();shutil.copy2(folder/'dist/KiwiImageEnlarge.exe',release)
        names=['README.txt','THIRD-PARTY-NOTICES.txt','PyInstaller-LICENSE.txt','OpenSSL-LICENSE.txt','stb-LICENSE.txt','upstream-pin.json',*pins['licenses']]
        for name in names:shutil.copy2(ROOT/name,release/name)
        shutil.copy2(ROOT.parents[1]/'LICENSE',release/'LICENSE')
        pillow=importlib.metadata.distribution('Pillow')
        licensefiles=[pillow.locate_file(p) for p in pillow.files if str(p).endswith('licenses/LICENSE')]
        if len(licensefiles)!=1:raise ValueError('Pillow license missing')
        shutil.copy2(licensefiles[0],release/'Pillow-LICENSE.txt')
        tcl=ROOT.parent/'common/tcl-8.6.15-LICENSE.terms'
        if hashlib.sha256(tcl.read_bytes()).hexdigest()!='c0a69a2bfd757361ec7e6143973b103c90409316b49e9c88db26ad6388e79f16':raise ValueError('Tcl license digest mismatch')
        texts=[]
        for title,p in [('Python',Path(sys.base_prefix)/'LICENSE.txt'),('Tcl8.6.15',tcl),('Tk',Path(sys.base_prefix)/'tcl/tk8.6/license.terms')]:texts.append('=== '+title+' ===\n'+p.read_text(encoding='utf8'))
        (release/'Runtime-LICENSES.txt').write_text('\n\n'.join(texts),encoding='utf8')
    out=ROOT/'KiwiImageEnlarge-0.1.0-win11-x64.zip'
    with zipfile.ZipFile(out,'w',zipfile.ZIP_DEFLATED,compresslevel=9) as z:
        for p in sorted(release.iterdir()):z.write(p,p.name)
    print('Built',out.name,out.stat().st_size,'SHA256',hashlib.sha256(out.read_bytes()).hexdigest())
if __name__=='__main__':build()
