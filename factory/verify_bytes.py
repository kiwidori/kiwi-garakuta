import ctypes,hashlib,importlib.util,json,os,subprocess,sys,tempfile,time,zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];APP=ROOT/'apps/kiwi-bytes';EXE=ROOT/'.tools/hexyl/hexyl.exe'
sys.path.insert(0,str(ROOT/'apps/common'));sys.path.insert(0,str(APP))
import runtime
from workbench import build_args
PROFILE=json.loads((APP/'profile.json').read_text(encoding='utf8'))
def load():
 spec=importlib.util.spec_from_file_location('kiwi_bytes',APP/'main.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
def cli():
 data=bytes(range(256));count=0
 def run(args,src=data):
  r=runtime.execute(EXE,args,stdin_data=src);assert r['returncode']==0,(args,r['stderr']);return r['stdout']
 for args in [['--length','16'],['--length','0x10'],['--length','1KiB'],['--skip','4','--length','8'],['--block-size','8','--skip','1block'],['--display-offset','0x100'],['--no-squeezing'],['--plain'],['--no-characters'],['--characters'],['--no-position'],['--include'],['--panels','1'],['--panels','auto'],['--terminal-width','100']]:assert run(['--color','never',*args]);count+=1
 for key,values in [('--color',['always','auto','never','force']),('--border',['unicode','ascii','none']),('--character-table',['default','ascii','codepage-1047','codepage-437','braille']),('--color-scheme',['default','gradient']),('--group-size',['1','2','4','8']),('--endianness',['big','little']),('--base',['binary','octal','decimal','hexadecimal'])]:
  for value in values:assert run([key,value]);count+=1
 assert b'00 01 02 03' in run(['--color','never','--border','ascii','--length','4'])
 out=run(['--color','never','--border','ascii','--skip','4','--length','4']);assert b'04 05 06 07' in out
 out=run(['--color','never','--plain','--group-size','2','--endianness','little','--length','4']);assert b'0100' in out and b'0302' in out;count+=3
 with tempfile.TemporaryDirectory() as td:
  p=Path(td)/'日本語.bin';p.write_bytes(data);before=p.read_bytes();r=runtime.execute(EXE,['--color','never','--skip=-4','--length','4','--',str(p)],stdin_data=None);assert r['returncode']==0 and b'fc fd fe ff' in r['stdout'];assert p.read_bytes()==before;count+=1
  large=Path(td)/'large.bin'
  with large.open('wb') as handle:handle.seek(1024*1024*1024);handle.write(b'Kiwi')
  r=runtime.execute(EXE,['--color','never','--skip=-4','--length','4','--',str(large)],stdin_data=None);assert r['returncode']==0 and b'4b 69 77 69' in r['stdout'];count+=1
 for shell in ['bash','elvish','fish','powershell','zsh']:assert run(['--completion',shell],b'');count+=1
 for arg in ['--help','--version','--print-color-table']:assert run([arg],b'');count+=1
 from unittest.mock import patch
 with patch.dict(os.environ,{'HEXYL_COLOR_NONASCII':'#ff00ff'}):assert b'38;2;255;0;255' in run(['--color','force'],b'\xff');count+=1
 bad=runtime.execute(EXE,['--length','bad'],stdin_data=b'');assert bad['returncode']!=0;count+=1
 defaults={f['flag']:f.get('default',False if f['type']=='bool' else '') for f in PROFILE['fields']};assert run(build_args(PROFILE,defaults,'UTF-8テキストを表示',[]),b'Kiwi')
 print('PASS real hexyl CLI',count,'checks including sparse 1GiB tail and inherited custom color')
def settle(app):
 limit=time.monotonic()+15
 while time.monotonic()<limit:
  app.root.update();time.sleep(.02)
  if (not app.worker or not app.worker.is_alive()) and app.q.empty() and app.last_result is not None:break
 assert app.last_result and 'stdout' in app.last_result,app.last_result
def gui():
 from unittest.mock import patch
 from PIL import ImageGrab
 m=load();app=m.BytesApp(PROFILE,APP);app.exe_path=str(EXE);app.advanced.exe_path=str(EXE)
 try:
  app._demo();app.run();settle(app);assert '4b' in app.out_text.get('1.0','end').lower();assert any(t.startswith('glow_') for t in app.out_text.tag_names());assert '\x1b' not in app.out_text.get('1.0','end')
  d=Path('C:/Users/Public/Documents/kiwi-bytes-demo');d.mkdir(parents=True,exist_ok=True);p=d/'サンプル.bin';p.write_bytes(bytes(range(32)));before=p.read_bytes()
  app.mode_var.set('ファイルを表示');app.in_text.delete('1.0','end');app.paths=[str(p)];app.path_list.insert('end',str(p));app.values['--skip'].set('-4');app.values['--length'].set('4');app.run();settle(app);assert b'1c' in app.last_result['stdout'];assert p.read_bytes()==before
  app._demo();app.values['--include'].set(True);app.run();settle(app);assert app.last_result['extension']=='.h' and b'0x4b' in app.last_result['stdout']
  app._demo();app.mode_var.set('UTF-8テキストを表示');app.in_text.delete('1.0','end');app.in_text.insert('1.0','Kiwi');app.run();settle(app);assert b'4b' in app.last_result['stdout']
  raw=d/'raw.txt';plain=d/'plain.txt';app._demo();app.run();settle(app)
  with patch('workbench.filedialog.asksaveasfilename',return_value=str(raw)),patch('workbench.messagebox.askyesno',return_value=True):app._save()
  with patch.object(m.filedialog,'asksaveasfilename',return_value=str(plain)),patch.object(m.messagebox,'askyesno',return_value=True):app._save_plain()
  assert raw.read_bytes()==app.last_result['stdout'];assert plain.read_bytes()==runtime._strip_ansi(app.last_result['stdout'].decode()).encode()
  for args,data,mode in [([],b'zz',{'hex_input':True}),([],b'0 1',{'hex_input':True}),(['--',str(p),str(p)],b'',{'files':True})]:app._worker(args,data,mode);assert app.q.get_nowait()[0]=='error'
  with patch.object(m.runtime,'execute',wraps=m.runtime.execute) as call:
   app._worker(['--version'],b'',{});assert app.q.get_nowait()[0]=='done';assert call.call_count==1
  app._worker(['--color','never','--skip','-4','--display-offset','0','--length','4','--',str(p)],b'',{'files':True});item=app.q.get_nowait();assert item[0]=='done' and item[4] and b'1c 1d 1e 1f' in item[2],item
  vals=['--skip','-4','--display-offset','-4','--',str(p)];assert runtime.normalize_hexyl_arguments(vals)==['--skip=-4','--display-offset=-4','--',str(p)];assert vals[1]=='-4'
  assert runtime.normalize_hexyl_arguments(['--skip','-4','--',str(p)])==['--skip=-4','--',str(p)]
  assert runtime.normalize_hexyl_arguments(['--','--skip','-4'])==['--','--skip','-4']
  r=runtime.execute(EXE,['--display-offset','-4','--',str(p)],stdin_data=None);assert r['returncode']!=0 and b'negative offset' in r['stderr']
  app._demo();app.run();settle(app);app.root.update();user32=ctypes.windll.user32;user32.GetAncestor.argtypes=[ctypes.c_void_p,ctypes.c_uint];user32.GetAncestor.restype=ctypes.c_void_p
  ImageGrab.grab(window=user32.GetAncestor(app.root.winfo_id(),2)).save(ROOT/'site/assets/screenshots/kiwi-bytes-public.png')
  app.advanced.open_window();app.root.update();assert app.advanced.option_tree.get_children();app.advanced._on_toplevel_close();app.root.update()
  app.mode_var.set('バージョン');app.run();settle(app);assert b'0.17.0' in app.last_result['stdout']
  print('PASS native binary/hex/C include/color GUI, file unchanged, raw/plain save, invalid input, screenshot, advanced, version')
 finally:app._on_close()
def portable():
 from verify_advanced_zip import windows,wait_window,user32
 from PyInstaller.archive.readers import CArchiveReader
 pin=json.loads((APP/'upstream-pin.json').read_text(encoding='utf8'));pkg=APP/f"{pin['app_exe']}-{pin['version']}-win11-x64.zip"
 with zipfile.ZipFile(pkg) as z,tempfile.TemporaryDirectory() as td:
  assert {'README.txt','LICENSE','UPSTREAM-LICENSE.txt','THIRD-PARTY-NOTICES.txt','Runtime-LICENSES.txt'}<=set(z.namelist());z.extractall(td)
  exe=Path(td)/'KiwiBytes.exe';a=CArchiveReader(str(exe));assert json.loads(a.extract('profile.json'))==PROFILE;assert hashlib.sha256(a.extract('hexyl.exe')).hexdigest()==pin['binary_sha']
  existing=windows();proc=subprocess.Popen([str(exe)])
  try:
   root=wait_window(PROFILE['title'],existing);sub=user32.GetSubMenu(user32.GetMenu(root),0);user32.PostMessageW(root,0x0111,user32.GetMenuItemID(sub,0),0)
   detail=wait_window('hexyl.exe - 詳細機能',existing);user32.PostMessageW(detail,0x0010,0,0);time.sleep(.2);user32.PostMessageW(root,0x0010,0,0);proc.wait(timeout=12);assert proc.returncode==0
  finally:
   if proc.poll() is None:subprocess.run(['taskkill','/F','/T','/PID',str(proc.pid)],capture_output=True)
 print('PASS portable ZIP licenses, binary pin, frozen main and advanced GUI, close')
if __name__=='__main__':globals()[sys.argv[1]]()
