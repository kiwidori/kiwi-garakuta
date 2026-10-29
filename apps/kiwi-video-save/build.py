"""Package the GUI and notices; the video engine is acquired separately."""
import hashlib,importlib.metadata,io,json,os,shutil,subprocess,sys,tempfile,urllib.request,zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parent
def build():
 if os.name!='nt' or sys.version_info[:3]!=(3,13,2):raise SystemExit('Build with Python3.13.2 on Windows x64.')
 if importlib.metadata.version('PyInstaller')!='6.22.2':raise ValueError('PyInstaller version mismatch')
 pin=json.loads((ROOT/'upstream-pin.json').read_text(encoding='utf8'))
 for name,digest in pin['licenses'].items():
  if hashlib.sha256((ROOT/name).read_bytes()).hexdigest()!=digest:raise ValueError('Notice digest mismatch: '+name)
 with tempfile.TemporaryDirectory(prefix='kiwi-video-save-build-') as td:
  folder=Path(td)
  spec=f'''a=Analysis([{str(ROOT/'main.py')!r}],pathex=[{str(ROOT)!r},{str(ROOT.parent/'common')!r}],binaries=[],datas=[],hiddenimports=[],hookspath=[],hooksconfig={{}},runtime_hooks=[],excludes=['PIL','numpy','matplotlib','IPython','cryptography','setuptools','pkg_resources','pytest','requests','yaml'],noarchive=False)
pyz=PYZ(a.pure)
exe=EXE(pyz,a.scripts,a.binaries,a.datas,[],name='KiwiVideoSave',debug=False,bootloader_ignore_signals=False,strip=False,upx=False,console=False,disable_windowed_traceback=False)
'''
  script=folder/'KiwiVideoSave.spec';script.write_text(spec,encoding='utf8')
  subprocess.run([sys.executable,'-m','PyInstaller','--noconfirm','--clean','--distpath',str(folder/'dist'),'--workpath',str(folder/'build'),str(script)],check=True)
  release=ROOT/'release'
  if release.is_symlink() or release.is_junction() or release.resolve().parent!=ROOT:raise ValueError('Unsafe release directory')
  if release.exists():shutil.rmtree(release)
  release.mkdir();shutil.copy2(folder/'dist/KiwiVideoSave.exe',release)
  for name in ['README.txt','upstream-pin.json',*pin['licenses']]:shutil.copy2(ROOT/name,release/name)
  shutil.copy2(ROOT.parents[1]/'LICENSE',release/'LICENSE')
  import tkinter
  if tkinter.Tcl().call('info','patchlevel')!='8.6.15':raise ValueError('Tcl notice mismatch')
  tcl=ROOT.parent/'common/tcl-8.6.15-LICENSE.terms'
  if hashlib.sha256(tcl.read_bytes()).hexdigest()!='c0a69a2bfd757361ec7e6143973b103c90409316b49e9c88db26ad6388e79f16':raise ValueError('Tcl notice digest mismatch')
  parts=[]
  for name,path in [('Python',Path(sys.base_prefix)/'LICENSE.txt'),('Tcl8.6.15',tcl),('Tk',Path(sys.base_prefix)/'tcl/tk8.6/license.terms')]:parts.append('=== '+name+' ===\n'+path.read_text(encoding='utf8'))
  (release/'Runtime-LICENSES.txt').write_text('\n\n'.join(parts),encoding='utf8')
 out=ROOT/'KiwiVideoSave-0.1.0-win11-x64.zip'
 with zipfile.ZipFile(out,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as z:
  for path in sorted(release.rglob('*')):
   if path.is_file():z.write(path,path.relative_to(release).as_posix())
 print('Built',out.name,out.stat().st_size,hashlib.sha256(out.read_bytes()).hexdigest())
if __name__=='__main__':build()
