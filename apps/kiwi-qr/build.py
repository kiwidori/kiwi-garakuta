"""Build a portable Windows GUI from hash-pinned official wheels."""
import hashlib,importlib.metadata,io,json,os,shutil,subprocess,sys,tempfile,zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT.parent/'common'))
from portable_build import fetch

def build():
 if os.name!='nt':raise SystemExit('Build on Windows x64.')
 for name,version in [('Pillow','12.3.0'),('PyInstaller','6.22.2')]:
  if importlib.metadata.version(name)!=version:raise ValueError('Runtime notice version mismatch: '+name)
 pin=json.loads((ROOT/'upstream-pin.json').read_text(encoding='utf8'))
 for name,digest in pin['licenses'].items():
  if hashlib.sha256((ROOT/name).read_bytes()).hexdigest()!=digest:raise ValueError('Notice digest mismatch: '+name)
 with tempfile.TemporaryDirectory(prefix='kiwi-qr-build-') as td:
  folder=Path(td);vendor=folder/'vendor';vendor.mkdir()
  for package in pin['packages']:
   cache=ROOT.parents[1]/'data/qr'/package['filename'];raw=cache.read_bytes() if os.environ.get('KIWI_USE_NATIVE_CACHE')=='1' else fetch(package['url'],package['sha256'])
   if hashlib.sha256(raw).hexdigest()!=package['sha256']:raise ValueError('Wheel digest mismatch')
   with zipfile.ZipFile(io.BytesIO(raw)) as z:
    for n in z.namelist():
     if not n.startswith(('qrcode/','zxingcpp/')) or n.endswith('/'):continue
     path=vendor/n
     if not path.resolve().is_relative_to(vendor.resolve()):raise ValueError('Unsafe wheel member')
     path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(z.read(n))
  if hashlib.sha256((vendor/'zxingcpp/zxingcpp.pyd').read_bytes()).hexdigest()!=pin['pyd_sha256']:raise ValueError('Native digest mismatch')
  spec=f'''a = Analysis([{str(ROOT/'main.py')!r}], pathex=[{str(vendor)!r},{str(ROOT)!r}], binaries=[], datas=[({str(ROOT/'upstream-pin.json')!r},'.'),({str(ROOT/'upstream-help.txt')!r},'.')], hiddenimports=['qrcode.image.svg','qrcode.image.styledpil','qrcode.image.styles.moduledrawers.pil','qrcode.image.styles.colormasks','zxingcpp'], hookspath=[], hooksconfig={{}}, runtime_hooks=[], excludes=['numpy','matplotlib','IPython','olefile','cv2','qrcode.console_scripts','colorama','png'], noarchive=False)
# The external Microsoft C++ runtime is a documented prerequisite.
a.binaries = [v for v in a.binaries if v[0].replace('\\\\','/').rsplit('/',1)[-1].lower() != 'msvcp140.dll']
pyz = PYZ(a.pure)
exe = EXE(pyz,a.scripts,a.binaries,a.datas,[],name='KiwiQR',debug=False,bootloader_ignore_signals=False,strip=False,upx=False,console=False,disable_windowed_traceback=False)
'''
  script=folder/'KiwiQR.spec';script.write_text(spec,encoding='utf8')
  subprocess.run([sys.executable,'-m','PyInstaller','--noconfirm','--clean','--distpath',str(folder/'dist'),'--workpath',str(folder/'build'),str(script)],check=True)
  release=ROOT/'release'
  if release.is_symlink() or release.is_junction() or release.resolve().parent!=ROOT:raise ValueError('Unsafe release directory')
  if release.exists():shutil.rmtree(release)
  release.mkdir();shutil.copy2(folder/'dist/KiwiQR.exe',release)
  for name in ['README.txt','upstream-pin.json',*pin['licenses']]:shutil.copy2(ROOT/name,release/name)
  shutil.copy2(ROOT.parents[1]/'LICENSE',release/'LICENSE')
  import tkinter
  if tkinter.Tcl().call('info','patchlevel')!='8.6.15':raise ValueError('Tcl notice mismatch')
  tcl=ROOT.parent/'common/tcl-8.6.15-LICENSE.terms'
  if hashlib.sha256(tcl.read_bytes()).hexdigest()!='c0a69a2bfd757361ec7e6143973b103c90409316b49e9c88db26ad6388e79f16':raise ValueError('Tcl notice digest mismatch')
  parts=[]
  for name,path in [('Python',Path(sys.base_prefix)/'LICENSE.txt'),('Tcl8.6.15',tcl),('Tk',Path(sys.base_prefix)/'tcl/tk8.6/license.terms')]:parts.append('=== '+name+' ===\n'+path.read_text(encoding='utf8'))
  (release/'Runtime-LICENSES.txt').write_text('\n\n'.join(parts),encoding='utf8')
 out=ROOT/'KiwiQR-0.1.0-win11-x64.zip'
 with zipfile.ZipFile(out,'w',zipfile.ZIP_DEFLATED,compresslevel=9) as z:
  for path in sorted(release.iterdir()):z.write(path,path.name)
 print('Built',out.name,out.stat().st_size,hashlib.sha256(out.read_bytes()).hexdigest())
if __name__=='__main__':build()
