"""Build the portable CPU OCR application from pinned official wheels."""
import hashlib,importlib.metadata,io,json,os,shutil,subprocess,sys,tempfile,zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT.parent/'common'))
from portable_build import fetch

def build():
 if os.name!='nt':raise SystemExit('Build on Windows x64.')
 for n,v in [('Pillow','12.3.0'),('PyInstaller','6.22.2')]:
  if importlib.metadata.version(n)!=v:raise ValueError('Runtime version mismatch: '+n)
 pin=json.loads((ROOT/'upstream-pin.json').read_text(encoding='utf8'))
 for n,digest in pin['licenses'].items():
  if hashlib.sha256((ROOT/n).read_bytes()).hexdigest()!=digest:raise ValueError('Notice digest mismatch: '+n)
 with tempfile.TemporaryDirectory(prefix='kiwi-ocr-build-') as td:
  folder=Path(td);vendor=folder/'vendor';vendor.mkdir()
  for pkg in pin['packages']:
   cache=ROOT.parents[1]/'data/ocr/wheels'/pkg['filename'];raw=cache.read_bytes() if os.environ.get('KIWI_USE_NATIVE_CACHE')=='1' else fetch(pkg['url'],pkg['sha256'])
   if hashlib.sha256(raw).hexdigest()!=pkg['sha256']:raise ValueError('Wheel digest mismatch')
   with zipfile.ZipFile(io.BytesIO(raw)) as z:
    for n in z.namelist():
     if n.endswith('/'):continue
     target=vendor/n
     if not target.resolve().is_relative_to(vendor.resolve()):raise ValueError('Unsafe wheel member')
     target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(z.read(n))
  datas=[(str(ROOT/'upstream-pin.json'),'.')]
  for n in ['config.yaml','default_models.yaml']:datas.append((str(vendor/'rapidocr'/n),'rapidocr'))
  for info in pin['models'].values():
   path=vendor/'rapidocr/models'/info['name']
   if hashlib.sha256(path.read_bytes()).hexdigest()!=info['sha256']:raise ValueError('Model digest mismatch')
   datas.append((str(path),'rapidocr/models'))
  for path in vendor.glob('*.dist-info'):datas.append((str(path),path.name))
  spec=f'''a = Analysis([{str(ROOT/'main.py')!r}], pathex=[{str(vendor)!r},{str(ROOT)!r}], binaries=[], datas={datas!r}, hiddenimports=['rapidocr.inference_engine.onnxruntime','rapidocr.inference_engine.onnxruntime.main','rapidocr.inference_engine.onnxruntime.provider_config','shapely','pyclipper','yaml','onnxruntime','omegaconf'], hookspath=[], hooksconfig={{}}, runtime_hooks=[], excludes=['torch','paddle','openvino','tensorrt','MNN','rapidocr.inference_engine.pytorch','rapidocr.inference_engine.paddle','rapidocr.inference_engine.openvino','rapidocr.inference_engine.tensorrt','rapidocr.inference_engine.mnn','matplotlib','IPython','scipy','pandas','pytest','cryptography','OpenSSL','attr','attrs','setuptools','pkg_resources','pip','wheel','chardet','simplejson','brotli','brotlicffi','zstandard','h2','hpack','hyperframe','sympy','onnx','typing_extensions'], noarchive=False)
def keep(v):
 path=v[0].replace('\\\\','/')
 n=path.rsplit('/',1)[-1].lower()
 if '/' not in path and n.startswith('geos') and n.endswith('.dll'):return False
 return not (n.startswith('msvcp140') or n.startswith('opencv_videoio_ffmpeg'))
a.binaries=[v for v in a.binaries if keep(v)]
a.datas=[v for v in a.datas if keep(v)]
pyz=PYZ(a.pure)
exe=EXE(pyz,a.scripts,[],exclude_binaries=True,name='KiwiOCR',debug=False,bootloader_ignore_signals=False,strip=False,upx=False,console=False,disable_windowed_traceback=False)
coll=COLLECT(exe,a.binaries,a.datas,strip=False,upx=False,name='KiwiOCR')
'''
  script=folder/'KiwiOCR.spec';script.write_text(spec,encoding='utf8')
  env=os.environ.copy();env['PYTHONPATH']=str(vendor)
  subprocess.run([sys.executable,'-m','PyInstaller','--noconfirm','--clean','--distpath',str(folder/'dist'),'--workpath',str(folder/'build'),str(script)],check=True,env=env)
  release=ROOT/'release'
  if release.is_symlink() or release.is_junction() or release.resolve().parent!=ROOT:raise ValueError('Unsafe release directory')
  if release.exists():shutil.rmtree(release)
  shutil.copytree(folder/'dist/KiwiOCR',release)
  for n in ['README.txt','upstream-pin.json',*pin['licenses']]:shutil.copy2(ROOT/n,release/n)
  shutil.copy2(ROOT.parents[1]/'LICENSE',release/'LICENSE')
  import tkinter
  if tkinter.Tcl().call('info','patchlevel')!='8.6.15':raise ValueError('Tcl notice mismatch')
  tcl=ROOT.parent/'common/tcl-8.6.15-LICENSE.terms'
  if hashlib.sha256(tcl.read_bytes()).hexdigest()!='c0a69a2bfd757361ec7e6143973b103c90409316b49e9c88db26ad6388e79f16':raise ValueError('Tcl digest mismatch')
  parts=[]
  for n,path in [('Python',Path(sys.base_prefix)/'LICENSE.txt'),('Tcl8.6.15',tcl),('Tk',Path(sys.base_prefix)/'tcl/tk8.6/license.terms')]:parts.append('=== '+n+' ===\n'+path.read_text(encoding='utf8'))
  (release/'Runtime-LICENSES.txt').write_text('\n\n'.join(parts),encoding='utf8')
 if os.environ.get('KIWI_DIRECTORY_ONLY')=='1':
  print('Built directory',release);return
 out=ROOT/'KiwiOCR-0.1.0-win11-x64.zip'
 with zipfile.ZipFile(out,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as z:
  for path in sorted(release.rglob('*')):
   if path.is_file():z.write(path,path.relative_to(release).as_posix())
 print('Built',out.name,out.stat().st_size,hashlib.sha256(out.read_bytes()).hexdigest())
if __name__=='__main__':build()
