"""Build the portable Windows GUI with pinned official Python wheels."""
import hashlib,io,json,os,shutil,subprocess,sys,tempfile,urllib.request,zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parent

def build():
    if os.name!='nt':raise SystemExit('Build on Windows 11 x64.')
    import tkinter
    if tkinter.Tcl().call('info','patchlevel')!='8.6.15':raise ValueError('Tcl version mismatch')
    pins=json.loads((ROOT/'dependency-pins.json').read_text(encoding='utf8'))
    with tempfile.TemporaryDirectory(prefix='kiwi-captions-build-') as td:
        folder=Path(td);vendor=folder/'vendor';vendor.mkdir()
        for pin in pins:
            req=urllib.request.Request(pin['url'],headers={'User-Agent':'kiwi-garakuta-build'})
            with urllib.request.urlopen(req,timeout=60) as response:body=response.read()
            if hashlib.sha256(body).hexdigest()!=pin['sha256']:raise ValueError('Wheel checksum mismatch: '+pin['name'])
            archive=zipfile.ZipFile(io.BytesIO(body))
            for name in archive.namelist():
                if not (vendor/name).resolve().is_relative_to(vendor):raise ValueError('Unsafe wheel member')
            archive.extractall(vendor)
        cmd=[sys.executable,'-m','PyInstaller','--noconfirm','--clean','--onefile','--noconsole','--name','KiwiYoutubeCaptions','--paths',str(vendor),'--collect-submodules','youtube_transcript_api','--collect-data','certifi','--distpath',str(folder/'dist'),'--workpath',str(folder/'build'),'--specpath',str(folder),str(ROOT/'main.py')]
        for name in ('chardet','zstandard','brotli','brotlicffi','OpenSSL','cryptography','socks','setuptools','pkg_resources','packaging','typing_extensions','wheel','_distutils_hack'):
            cmd[-1:-1]=['--exclude-module',name]
        subprocess.run(cmd,check=True,env={**os.environ,'PYTHONPATH':str(vendor)})
        release=ROOT/'release'
        if release.is_symlink() or release.is_junction() or release.resolve().parent!=ROOT:raise ValueError('Unsafe release directory')
        if release.exists():shutil.rmtree(release)
        release.mkdir();shutil.copy2(folder/'dist/KiwiYoutubeCaptions.exe',release/'KiwiYoutubeCaptions.exe')
        for name in ('README.txt','THIRD-PARTY-NOTICES.txt'):shutil.copy2(ROOT/name,release/name)
        shutil.copy2(ROOT.parents[1]/'LICENSE',release/'LICENSE')
        tcl=ROOT.parent/'common/tcl-8.6.15-LICENSE.terms'
        if hashlib.sha256(tcl.read_bytes()).hexdigest()!='c0a69a2bfd757361ec7e6143973b103c90409316b49e9c88db26ad6388e79f16':raise ValueError('Tcl license digest mismatch')
        texts=[]
        for name,path in [('Python',Path(sys.base_prefix)/'LICENSE.txt'),('Tcl 8.6.15',tcl),('Tk',Path(sys.base_prefix)/'tcl/tk8.6/license.terms')]:texts.append('=== '+name+' ===\n'+path.read_text(encoding='utf8'))
        (release/'Runtime-LICENSES.txt').write_text('\n\n'.join(texts),encoding='utf8')
    package=ROOT/'KiwiYoutubeCaptions-0.1.0-win11-x64.zip'
    with zipfile.ZipFile(package,'w',zipfile.ZIP_DEFLATED,compresslevel=9) as archive:
        for p in sorted(release.iterdir()):archive.write(p,p.name)
    print('Built',package.name,package.stat().st_size,'SHA256',hashlib.sha256(package.read_bytes()).hexdigest())
if __name__=='__main__':build()
