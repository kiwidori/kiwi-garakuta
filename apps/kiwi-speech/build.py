"""Build the portable interface without bundling the speech engine or model."""
import hashlib,importlib.metadata,json,os,shutil,subprocess,sys,tempfile,zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parent

def build():
 if os.name!='nt' or sys.version_info[:3]!=(3,13,2):raise SystemExit('Build with Python3.13.2 on Windows x64.')
 if importlib.metadata.version('PyInstaller')!='6.22.2':raise ValueError('PyInstaller version mismatch')
 for name,digest in json.loads((ROOT/'notice-pins.json').read_text(encoding='utf8')).items():
  if hashlib.sha256((ROOT/name).read_bytes()).hexdigest()!=digest:raise ValueError('Notice digest mismatch: '+name)
 for name,digest in json.loads((ROOT/'build-sources.json').read_text(encoding='utf8')).items():
  if hashlib.sha256((ROOT.parent/'common'/name).read_bytes().replace(b'\r\n',b'\n')).hexdigest()!=digest:raise ValueError('Shared source mismatch: '+name)
 with tempfile.TemporaryDirectory(prefix='kiwi-speech-build-') as td:
  folder=Path(td)
  spec=f'''a=Analysis([{str(ROOT/'main.py')!r}],pathex=[{str(ROOT)!r},{str(ROOT.parent/'common')!r}],binaries=[],datas=[],hiddenimports=[],hookspath=[],hooksconfig={{}},runtime_hooks=[],excludes=['PIL','numpy','matplotlib','IPython','cryptography','setuptools','pkg_resources','pytest','requests','yaml','certifi','runtime','advanced','process_tree'],noarchive=False)
pyz=PYZ(a.pure)
exe=EXE(pyz,a.scripts,a.binaries,a.datas,[],name='KiwiSpeech',debug=False,bootloader_ignore_signals=False,strip=False,upx=False,console=False,disable_windowed_traceback=False)
'''
  script=folder/'KiwiSpeech.spec';script.write_text(spec,encoding='utf8')
  subprocess.run([sys.executable,'-m','PyInstaller','--noconfirm','--clean','--distpath',str(folder/'dist'),'--workpath',str(folder/'build'),str(script)],check=True)
  release=ROOT/'release'
  if release.is_symlink() or release.is_junction() or release.resolve().parent!=ROOT:raise ValueError('Unsafe release directory')
  if release.exists():shutil.rmtree(release)
  release.mkdir();shutil.copy2(folder/'dist/KiwiSpeech.exe',release)
  for p in ROOT.glob('*.txt'):shutil.copy2(p,release/p.name)
  for name in ['notice-pins.json','build-sources.json']:shutil.copy2(ROOT/name,release/name)
  shutil.copy2(ROOT/'sherpa-onnx-c-api.h',release/'sherpa-onnx-c-api.h')
  for name in ['engine','voice']:shutil.copytree(ROOT/name,release/name)
  shutil.copy2(ROOT.parents[1]/'LICENSE',release/'LICENSE')
  import tkinter
  if tkinter.Tcl().call('info','patchlevel')!='8.6.15':raise ValueError('Tcl version mismatch')
  tcl=ROOT.parent/'common/tcl-8.6.15-LICENSE.terms'
  if hashlib.sha256(tcl.read_bytes()).hexdigest()!='c0a69a2bfd757361ec7e6143973b103c90409316b49e9c88db26ad6388e79f16':raise ValueError('Tcl license mismatch')
  texts=[]
  for name,p in [('Python',Path(sys.base_prefix)/'LICENSE.txt'),('Tcl8.6.15',tcl),('Tk',Path(sys.base_prefix)/'tcl/tk8.6/license.terms')]:texts.append('=== '+name+' ===\n'+p.read_text(encoding='utf8'))
  (release/'Runtime-LICENSES.txt').write_text('\n\n'.join(texts),encoding='utf8')
 output=ROOT/'KiwiSpeech-0.1.0-win11-x64.zip'
 with zipfile.ZipFile(output,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as z:
  for p in sorted(release.rglob('*')):
   if p.is_file():z.write(p,p.relative_to(release).as_posix())
 print('Built',output.name,output.stat().st_size,hashlib.sha256(output.read_bytes()).hexdigest())
if __name__=='__main__':build()
