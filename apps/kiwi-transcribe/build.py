"""Build the portable Windows speech transcription application."""
import hashlib,io,json,os,shutil,subprocess,sys,tempfile,zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT.parent/'common'))
from portable_build import fetch
def build():
    if os.name!='nt':raise SystemExit('Build on Windows x64.')
    pin=json.loads((ROOT/'upstream-pin.json').read_text(encoding='utf8'));data=ROOT.parents[1]/'data/speech'
    cached=os.environ.get('KIWI_USE_NATIVE_CACHE')=='1'
    raw=(data/'upstream.zip').read_bytes() if cached else fetch(pin['url'],pin['sha256'])
    if hashlib.sha256(raw).hexdigest()!=pin['sha256']:raise ValueError('Native archive digest mismatch')
    for name,digest in pin['licenses'].items():
        if hashlib.sha256((ROOT/name).read_bytes()).hexdigest()!=digest:raise ValueError('Notice digest mismatch: '+name)
    with tempfile.TemporaryDirectory(prefix='kiwi-transcribe-build-') as td:
        folder=Path(td);payload=folder/'native-payload.zip'
        with zipfile.ZipFile(payload,'w',zipfile.ZIP_STORED) as z,zipfile.ZipFile(io.BytesIO(raw)) as archive:
            for name,digest in pin['members'].items():
                if '/' in name or '\\' in name:raise ValueError('Unsafe native member')
                body=archive.read(pin['prefix']+name)
                if hashlib.sha256(body).hexdigest()!=digest:raise ValueError('Native member digest mismatch')
                z.writestr(name,body)
            caches={'small.bin':data/'ggml-small-q5_1.bin','silero.bin':data/'vad.bin'}
            if set(pin['models'])!=set(caches):raise ValueError('Unexpected model selection')
            for name,p in pin['models'].items():
                body=caches[name].read_bytes() if cached else fetch(p['url'],p['sha256'])
                if len(body)!=p['size'] or hashlib.sha256(body).hexdigest()!=p['sha256']:raise ValueError('Model digest mismatch')
                z.writestr(name,body)
        args=[sys.executable,'-m','PyInstaller','--noconfirm','--clean','--onefile','--noconsole','--paths',str(ROOT.parent/'common'),'--name','KiwiTranscribe','--distpath',str(folder/'dist'),'--workpath',str(folder/'build'),'--specpath',str(folder)]
        for f in (payload,ROOT/'upstream-pin.json',ROOT/'upstream-help.txt',ROOT/'languages.json'):args+=['--add-data',str(f)+os.pathsep+'.']
        for mod in ('numpy','matplotlib','IPython'):args+=['--exclude-module',mod]
        subprocess.run([*args,str(ROOT/'main.py')],check=True)
        release=ROOT/'release'
        if release.is_symlink() or release.is_junction() or release.resolve().parent!=ROOT:raise ValueError('Unsafe release directory')
        if release.exists():shutil.rmtree(release)
        release.mkdir();shutil.copy2(folder/'dist/KiwiTranscribe.exe',release)
        for name in ('README.txt','THIRD-PARTY-NOTICES.txt','upstream-pin.json',*pin['licenses']):shutil.copy2(ROOT/name,release/name)
        shutil.copy2(ROOT.parents[1]/'LICENSE',release/'LICENSE')
        import tkinter
        if tkinter.Tcl().call('info','patchlevel')!='8.6.15':raise ValueError('Tcl notice version mismatch')
        tcl=ROOT.parent/'common/tcl-8.6.15-LICENSE.terms'
        if hashlib.sha256(tcl.read_bytes()).hexdigest()!='c0a69a2bfd757361ec7e6143973b103c90409316b49e9c88db26ad6388e79f16':raise ValueError('Tcl notice digest mismatch')
        notices=[]
        for title,p in [('Python',Path(sys.base_prefix)/'LICENSE.txt'),('Tcl8.6.15',tcl),('Tk',Path(sys.base_prefix)/'tcl/tk8.6/license.terms')]:notices.append('=== '+title+' ===\n'+p.read_text(encoding='utf8'))
        (release/'Runtime-LICENSES.txt').write_text('\n\n'.join(notices),encoding='utf8')
    out=ROOT/'KiwiTranscribe-0.1.0-win11-x64.zip'
    with zipfile.ZipFile(out,'w',zipfile.ZIP_DEFLATED,compresslevel=9) as z:
        for p in sorted(release.iterdir()):z.write(p,p.name)
    print('Built',out.name,out.stat().st_size,hashlib.sha256(out.read_bytes()).hexdigest())
if __name__=='__main__':build()
