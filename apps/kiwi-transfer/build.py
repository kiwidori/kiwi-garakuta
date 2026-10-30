"""Build Windows portable GUI with pinned upstream and complete notices."""
import hashlib,importlib.metadata,io,json,os,shutil,subprocess,sys,tempfile,zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT.parent/'common'))
from portable_build import fetch
def build():
    if os.name!='nt':raise SystemExit('Build on Windows x64.')
    if sys.version_info[:3]!=(3,13,2) or importlib.metadata.version('PyInstaller')!='6.22.2':raise ValueError('Runtime versions differ from notices')
    pin=json.loads((ROOT/'upstream-pin.json').read_text(encoding='utf8'))
    browser=ROOT/'browser-engine';browser_pin=json.loads((browser/'upstream-pin.json').read_text(encoding='utf8'))
    source_pin=json.loads((ROOT/'source-manifest.json').read_text(encoding='utf8'))
    for name,digest in source_pin.items():
        if hashlib.sha256((ROOT/name).read_bytes()).hexdigest()!=digest:raise ValueError('Source digest mismatch: '+name)
    for name,digest in browser_pin['licenses'].items():
        if hashlib.sha256((browser/name).read_bytes()).hexdigest()!=digest:raise ValueError('Browser notice digest mismatch: '+name)
    cache=ROOT.parents[1]/'data/croc/upstream.zip'
    raw=cache.read_bytes() if os.environ.get('KIWI_USE_NATIVE_CACHE')=='1' else fetch(pin['url'],pin['sha256'])
    if hashlib.sha256(raw).hexdigest()!=pin['sha256']:raise ValueError('Archive digest mismatch')
    for name,digest in pin['licenses'].items():
        if hashlib.sha256((ROOT/name).read_bytes()).hexdigest()!=digest:raise ValueError('Notice digest mismatch: '+name)
    with tempfile.TemporaryDirectory(prefix='kiwi-transfer-build-') as td:
        folder=Path(td);payload=folder/'native-payload.zip'
        binary=zipfile.ZipFile(io.BytesIO(raw)).read('croc.exe')
        if hashlib.sha256(binary).hexdigest()!=pin['native_sha256']:raise ValueError('Binary digest mismatch')
        with zipfile.ZipFile(payload,'w',zipfile.ZIP_STORED) as z:z.writestr('croc.exe',binary)
        browser_cache=ROOT.parents[1]/'data/cycle-qrcp/qrcp_0.11.7_windows_amd64.zip'
        browser_raw=browser_cache.read_bytes() if os.environ.get('KIWI_USE_NATIVE_CACHE')=='1' else fetch(browser_pin['url'],browser_pin['sha256'])
        if hashlib.sha256(browser_raw).hexdigest()!=browser_pin['sha256']:raise ValueError('Browser archive digest mismatch')
        browser_binary=zipfile.ZipFile(io.BytesIO(browser_raw)).read('qrcp.exe')
        if hashlib.sha256(browser_binary).hexdigest()!=browser_pin['native_sha256']:raise ValueError('Browser native digest mismatch')
        browser_bundle=folder/'browser-engine';browser_bundle.mkdir()
        with zipfile.ZipFile(browser_bundle/'native-payload.zip','w',zipfile.ZIP_STORED) as z:z.writestr('qrcp.exe',browser_binary)
        for name in ('upstream-pin.json',*browser_pin['licenses']):shutil.copy2(browser/name,browser_bundle/name)
        vendor=folder/'vendor';vendor.mkdir()
        for package in browser_pin['packages']:
            wheel_cache=ROOT.parents[1]/'data/qr'/package['filename']
            wheel=wheel_cache.read_bytes() if os.environ.get('KIWI_USE_NATIVE_CACHE')=='1' else fetch(package['url'],package['sha256'])
            if hashlib.sha256(wheel).hexdigest()!=package['sha256']:raise ValueError('QR wheel digest mismatch')
            with zipfile.ZipFile(io.BytesIO(wheel)) as z:
                for name in z.namelist():
                    if not name.startswith('qrcode/') or name.endswith('/'):continue
                    dest=vendor/name
                    if not dest.resolve().is_relative_to(vendor.resolve()):raise ValueError('Unsafe wheel member')
                    dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(z.read(name))
        args=[sys.executable,'-m','PyInstaller','--noconfirm','--clean','--onefile','--noconsole','--paths',str(vendor),'--paths',str(ROOT),'--name','KiwiTransfer','--distpath',str(folder/'dist'),'--workpath',str(folder/'build'),'--specpath',str(folder)]
        for excluded in ('PIL','numpy','matplotlib','IPython','qrcode.console_scripts','colorama','png','runtime','advanced','process_tree'):args+=['--exclude-module',excluded]
        for file in (payload,ROOT/'upstream-pin.json',ROOT/'upstream-help.txt',ROOT/'source-manifest.json'):args+=['--add-data',str(file)+os.pathsep+'.']
        args+=['--add-data',str(browser_bundle)+os.pathsep+'browser-engine']
        subprocess.run([*args,str(ROOT/'main.py')],check=True)
        release=ROOT/'release'
        if release.is_symlink() or release.is_junction() or release.resolve().parent!=ROOT:raise ValueError('Unsafe release path')
        if release.exists():shutil.rmtree(release)
        release.mkdir();shutil.copy2(folder/'dist/KiwiTransfer.exe',release)
        for name in ['README.txt','THIRD-PARTY-NOTICES.txt','upstream-pin.json',*pin['licenses']]:shutil.copy2(ROOT/name,release/name)
        shutil.copy2(ROOT/'source-manifest.json',release/'source-manifest.json')
        (release/'browser-engine').mkdir()
        for name in ('upstream-pin.json',*browser_pin['licenses']):shutil.copy2(browser/name,release/'browser-engine'/name)
        shutil.copy2(ROOT.parents[1]/'LICENSE',release/'LICENSE')
        import tkinter
        if tkinter.Tcl().call('info','patchlevel')!='8.6.15':raise ValueError('Tcl license mismatch')
        tcl=ROOT.parent/'common/tcl-8.6.15-LICENSE.terms'
        if hashlib.sha256(tcl.read_bytes()).hexdigest()!='c0a69a2bfd757361ec7e6143973b103c90409316b49e9c88db26ad6388e79f16':raise ValueError('Tcl notice mismatch')
        parts=[]
        for title,file in [('Python',Path(sys.base_prefix)/'LICENSE.txt'),('Tcl8.6.15',tcl),('Tk',Path(sys.base_prefix)/'tcl/tk8.6/license.terms')]:parts.append('=== '+title+' ===\n'+file.read_text(encoding='utf8'))
        (release/'Runtime-LICENSES.txt').write_text('\n\n'.join(parts),encoding='utf8')
    out=ROOT/'KiwiTransfer-0.2.0-win11-x64.zip'
    with zipfile.ZipFile(out,'w',zipfile.ZIP_DEFLATED,compresslevel=9) as z:
        for file in sorted(release.rglob('*')):
            if file.is_file():z.write(file,file.relative_to(release).as_posix())
    print('Built',out.name,out.stat().st_size,hashlib.sha256(out.read_bytes()).hexdigest())
if __name__=='__main__':build()
