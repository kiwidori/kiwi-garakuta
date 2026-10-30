"""Build the editor and page exporter with pinned native payloads and notices."""
import ctypes
import hashlib
import importlib.metadata
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parent


def compile_host(destination):
    buffer = ctypes.create_unicode_buffer(32768)
    if not ctypes.windll.kernel32.GetWindowsDirectoryW(buffer, len(buffer)):
        raise ValueError('Windows directory is unavailable')
    compiler = Path(buffer.value)/'Microsoft.NET/Framework64/v4.0.30319/csc.exe'
    if not compiler.is_file():
        raise ValueError('Windows .NET Framework C# compiler is unavailable')
    subprocess.run([str(compiler), '/nologo', '/platform:x64', '/target:exe', '/optimize+',
                    '/out:'+str(destination), str(ROOT/'PdfHost.cs')], check=True)


def prepare_native(destination):
    pin = json.loads((ROOT/'upstream-pin.json').read_text(encoding='utf8'))
    cache = ROOT.parents[1]/'data/pdf-workbench/qpdf-12.4.2-msvc64.zip'
    if not cache.exists():
        urllib.request.urlretrieve(pin['url'], cache)
    raw = cache.read_bytes()
    if hashlib.sha256(raw).hexdigest() != pin['sha256']:
        raise ValueError('Native archive mismatch')
    destination.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        for name, digest in pin['members'].items():
            if name not in {'qpdf.exe', 'qpdf30.dll'}:
                raise ValueError('Unexpected native member')
            data = archive.read(pin['prefix']+name)
            if hashlib.sha256(data).hexdigest() != digest:
                raise ValueError('Native member mismatch')
            (destination/name).write_bytes(data)
    compile_host(destination/'KiwiPdfHost.exe')


def build():
    if os.name != 'nt' or sys.version_info[:3] != (3,13,2):
        raise ValueError('Build with Python 3.13.2 on Windows x64')
    if importlib.metadata.version('PyInstaller') != '6.22.2':
        raise ValueError('PyInstaller version mismatch')
    pin = json.loads((ROOT/'upstream-pin.json').read_text(encoding='utf8'))
    manifest = json.loads((ROOT/'build-manifest.json').read_text(encoding='utf8'))
    for name, record in pin['licenses'].items():
        if hashlib.sha256((ROOT/name).read_bytes()).hexdigest() != record['sha256']:
            raise ValueError('Notice digest mismatch: '+name)
    for name, digest in manifest['files'].items():
        if hashlib.sha256((ROOT/name).read_bytes()).hexdigest() != digest:
            raise ValueError('Build manifest mismatch: '+name)
    stamp_pin = json.loads((ROOT/'stamp-engine/upstream-pin.json').read_text(encoding='utf8'))
    import PIL
    if PIL.__version__ != stamp_pin['pillow_version']:
        raise ValueError('Pillow version mismatch')
    for name, digest in stamp_pin['pillow_binaries'].items():
        if hashlib.sha256((Path(PIL.__file__).parent/name).read_bytes()).hexdigest() != digest:
            raise ValueError('Pillow binary mismatch')
    for name, digest in json.loads((ROOT/'common-sources.json').read_text(encoding='utf8')).items():
        if hashlib.sha256((ROOT.parent/'common'/name).read_bytes().replace(b'\r\n',b'\n')).hexdigest() != digest:
            raise ValueError('Shared source mismatch')
    with tempfile.TemporaryDirectory(prefix='kiwi-pdf-workbench-build-') as td:
        folder = Path(td)
        native = folder/'native'
        prepare_native(native)
        host = native/'KiwiPdfHost.exe'
        hostpin = folder/'host-pin.json'
        hostpin.write_text(json.dumps({'sha256':hashlib.sha256(host.read_bytes()).hexdigest(),
                                      'source_sha256':hashlib.sha256((ROOT/'PdfHost.cs').read_bytes()).hexdigest()}), encoding='utf8')
        payload = folder/'native-payload.zip'
        with zipfile.ZipFile(payload, 'w', zipfile.ZIP_STORED) as z:
            for name in [*pin['members'], 'KiwiPdfHost.exe']:
                z.write(native/name, name)
        datas = [(str(payload),'.'),(str(hostpin),'.')]
        datas += [(str(ROOT/name),'.') for name in ['upstream-pin.json','job-schema.json','upstream-help.txt']]
        spec = f'''a=Analysis([{str(ROOT/'main.py')!r}],pathex=[{str(ROOT)!r},{str(ROOT.parent/'common')!r}],binaries=[],datas={datas!r},hiddenimports=[],hookspath=[],hooksconfig={{}},runtime_hooks=[],excludes=['numpy','matplotlib','IPython','cryptography','setuptools','pkg_resources','pytest','requests','yaml'],noarchive=False)
pyz=PYZ(a.pure)
exe=EXE(pyz,a.scripts,a.binaries,a.datas,[],name='KiwiPDFWorkbench',debug=False,bootloader_ignore_signals=False,strip=False,upx=False,console=False,disable_windowed_traceback=False)
'''
        script = folder/'KiwiPDFWorkbench.spec'
        script.write_text(spec,encoding='utf8')
        subprocess.run([sys.executable,'-m','PyInstaller','--noconfirm','--clean','--distpath',str(folder/'dist'),
                        '--workpath',str(folder/'build'),str(script)],check=True)
        release = ROOT/'release'
        if release.is_symlink() or release.is_junction() or release.resolve().parent != ROOT:
            raise ValueError('Unsafe release directory')
        if release.exists():
            shutil.rmtree(release)
        release.mkdir()
        shutil.copy2(folder/'dist/KiwiPDFWorkbench.exe',release)
        names = {'README.txt','THIRD-PARTY-NOTICES.txt','PyInstaller-LICENSE.txt','Python-OpenSSL-LICENSE.txt',
                 'MuPDF-LICENSE.txt','upstream-pin.json','image-engine/upstream-pin.json','build-manifest.json','PdfHost.cs',*pin['licenses']}
        names.update('stamp-engine/'+p.name for p in (ROOT/'stamp-engine').iterdir() if p.is_file())
        names.add('common-sources.json')
        for name in names:
            dest = release/name
            dest.parent.mkdir(parents=True,exist_ok=True)
            shutil.copy2(ROOT/name,dest)
        shutil.copy2(hostpin,release/'host-pin.json')
        shutil.copy2(ROOT.parents[1]/'LICENSE',release/'LICENSE')
        import tkinter
        if tkinter.Tcl().call('info','patchlevel') != '8.6.15':
            raise ValueError('Tcl version mismatch')
        tcl = ROOT.parent/'common/tcl-8.6.15-LICENSE.terms'
        if hashlib.sha256(tcl.read_bytes()).hexdigest() != 'c0a69a2bfd757361ec7e6143973b103c90409316b49e9c88db26ad6388e79f16':
            raise ValueError('Tcl notice mismatch')
        texts = []
        for name,path in [('Python',Path(sys.base_prefix)/'LICENSE.txt'),('Tcl8.6.15',tcl),('Tk',Path(sys.base_prefix)/'tcl/tk8.6/license.terms')]:
            texts.append('=== '+name+' ===\n'+path.read_text(encoding='utf8'))
        (release/'Runtime-LICENSES.txt').write_text('\n\n'.join(texts),encoding='utf8')
    out = ROOT/'KiwiPDFWorkbench-0.2.0-win11-x64.zip'
    with zipfile.ZipFile(out,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        for path in sorted(release.rglob('*')):
            if path.is_file():
                z.write(path,path.relative_to(release).as_posix())
    print('Built',out.name,out.stat().st_size,hashlib.sha256(out.read_bytes()).hexdigest())


if __name__ == '__main__':
    build()
