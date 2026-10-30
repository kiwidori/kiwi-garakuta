"""Make the installed Microsoft runtime available to the GEOS DLL alias."""
import ctypes,hashlib,os,sys,tempfile
from pathlib import Path
_HANDLES=[]

def prepare():
 if os.name!='nt' or not getattr(sys,'frozen',False):return
 aliases=['msvcp140-0fa7eb792d3fbcf2233e4ea47e9144b9.dll','msvcp140-a4c2229bdc2a2a630acdc095b4d86008.dll']
 buffer=ctypes.create_unicode_buffer(32768)
 if not ctypes.windll.kernel32.GetSystemDirectoryW(buffer,len(buffer)):raise OSError('Windowsのシステムフォルダーを取得できません。')
 source=Path(buffer.value)/'msvcp140.dll'
 if not source.is_file():raise RuntimeError('Microsoft Visual C++ v14再頒布可能パッケージ（x64）をインストールしてください。')
 raw=source.read_bytes();digest=hashlib.sha256(raw).hexdigest();cache=Path(tempfile.gettempdir())/'kiwi-ocr-runtime'/digest;cache.mkdir(parents=True,exist_ok=True)
 for alias in aliases:
  target=cache/alias
  if not target.exists():
   fd,name=tempfile.mkstemp(prefix='runtime-',dir=cache)
   try:
    with os.fdopen(fd,'wb') as f:f.write(raw)
    try:os.link(name,target)
    except FileExistsError:pass
   finally:Path(name).unlink(missing_ok=True)
  if hashlib.sha256(target.read_bytes()).hexdigest()!=digest:raise RuntimeError('ランタイム用キャッシュの検証に失敗しました。')
 _HANDLES.append(os.add_dll_directory(str(cache)))
