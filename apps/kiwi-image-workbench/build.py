"""Build the portable image editor with the pinned PNG optimizer."""
import hashlib,importlib.metadata,io,json,os,shutil,subprocess,sys,tempfile,urllib.request,zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parent
SHARED={'advanced.py':'c88fcf134343f1ec61ebb15c23b7851b70dcd9b4ec6258b3ad968582d168fd64','runtime.py':'7ba8b0da79c858b4a93bc7eb157e97817b76f9668d7640a68879c980dc6c7aa8'}
PNG_URL='https://github.com/oxipng/oxipng/releases/download/v10.2.1/oxipng-10.2.1-x86_64-pc-windows-msvc.zip'
PNG_SHA='7e940f83ee46874b73f53031f96a15834cb70b220af27391fb06fe7b4dd798e1'
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def build():
 if os.name!='nt' or sys.version_info[:3]!=(3,13,2):raise ValueError('Build with Windows x64 Python 3.13.2')
 if importlib.metadata.version('PyInstaller')!='6.22.2':raise ValueError('PyInstaller version mismatch')
 common=ROOT.parent/'common'
 for name,digest in SHARED.items():
  if sha(common/name)!=digest:raise ValueError('Shared source digest mismatch: '+name)
 pin=json.loads((ROOT/'upstream-pin.json').read_text(encoding='utf8'))
 import PIL
 if PIL.__version__!=pin['pillow_version']:raise ValueError('Pillow version mismatch')
 for name,digest in pin['pillow_binaries'].items():
  if sha(Path(PIL.__file__).parent/name)!=digest:raise ValueError('Pillow binary digest mismatch')
 for name,digest in pin['licenses'].items():
  if sha(ROOT/name)!=digest:raise ValueError('Notice digest mismatch: '+name)
 for name,digest in json.loads((ROOT/'build-sources.json').read_text(encoding='utf8')).items():
  if sha(ROOT/name)!=digest:raise ValueError('Additional notice mismatch: '+name)
 request=urllib.request.Request(PNG_URL,headers={'User-Agent':'KiwiImageWorkbench/0.1'})
 with urllib.request.urlopen(request,timeout=45) as response:data=response.read(8*1024*1024)
 if hashlib.sha256(data).hexdigest()!=PNG_SHA:raise ValueError('oxipng archive digest mismatch')
 with tempfile.TemporaryDirectory(prefix='kiwi-image-png-build-') as td:
  folder=Path(td);native=folder/'png';native.mkdir()
  with zipfile.ZipFile(io.BytesIO(data)) as archive:
   for name in ['oxipng.exe','LICENSE.txt','README.md']:(native/name).write_bytes(archive.read('oxipng-10.2.1-x86_64-pc-windows-msvc/'+name))
  spec=f'''a=Analysis([{str(ROOT/'main.py')!r}],pathex=[{str(ROOT)!r},{str(common)!r}],binaries=[({str(native/'oxipng.exe')!r},'png')],datas=[({str(ROOT/'png/advanced-spec.json')!r},'png'),({str(ROOT/'png/upstream-help.txt')!r},'png')],hiddenimports=[],hookspath=[],hooksconfig={{}},runtime_hooks=[],excludes=['numpy','matplotlib','IPython','cryptography','setuptools','pkg_resources','pytest','requests','yaml'],noarchive=False)
pyz=PYZ(a.pure)
exe=EXE(pyz,a.scripts,a.binaries,a.datas,[],name='KiwiImageWorkbench',debug=False,bootloader_ignore_signals=False,strip=False,upx=False,console=False,disable_windowed_traceback=False)
'''
  script=folder/'KiwiImageWorkbench.spec';script.write_text(spec,encoding='utf8')
  subprocess.run([sys.executable,'-m','PyInstaller','--noconfirm','--clean','--distpath',str(folder/'dist'),'--workpath',str(folder/'build'),str(script)],check=True)
  release=ROOT/'release'
  if release.is_symlink() or release.is_junction() or release.resolve().parent!=ROOT:raise ValueError('Unsafe release directory')
  if release.exists():shutil.rmtree(release)
  release.mkdir();shutil.copy2(folder/'dist/KiwiImageWorkbench.exe',release)
  for name in ['README.txt','upstream-pin.json','build-sources.json','OpenSSL-LICENSE.txt',*pin['licenses']]:shutil.copy2(ROOT/name,release/name)
  (release/'oxipng-LICENSE.txt').write_bytes((native/'LICENSE.txt').read_bytes())
  (release/'oxipng-README.md').write_bytes((native/'README.md').read_bytes())
  (release/'PNG-NOTICES.txt').write_text('oxipng 10.2.1: MIT License. See oxipng-LICENSE.txt and oxipng-README.md.\nUnofficial GUI. https://github.com/oxipng/oxipng\nOfficial Windows archive: '+PNG_URL+'\nSHA-256: '+PNG_SHA+'\n',encoding='utf8')
  shutil.copy2(ROOT.parents[1]/'LICENSE',release/'LICENSE')
  sys.path.insert(0,str(common));from runtime_licenses import write_runtime_licenses
  write_runtime_licenses(release/'Runtime-LICENSES.txt')
 out=ROOT/'KiwiImageWorkbench-0.1.0-win11-x64.zip'
 with zipfile.ZipFile(out,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as archive:
  for path in sorted(release.rglob('*')):
   if path.is_file():archive.write(path,path.relative_to(release).as_posix())
 print('Built',out.name,out.stat().st_size,sha(out))
if __name__=='__main__':build()
