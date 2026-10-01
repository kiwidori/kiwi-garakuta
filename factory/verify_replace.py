import ctypes,hashlib,importlib.util,io,json,subprocess,sys,tempfile,threading,time,zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];APP=ROOT/'apps/kiwi-replace';EXE=ROOT/'.tools/sd/sd.exe'
sys.path.insert(0,str(ROOT/'apps/common'))
import runtime
PROFILE=json.loads((APP/'profile.json').read_text(encoding='utf8'))
def load():
 spec=importlib.util.spec_from_file_location('kiwi_replace',APP/'main.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
def options(**kwargs):
 result={f['flag']:f.get('default',False if f['type']=='bool' else '') for f in PROFILE['fields']};result.update(kwargs);return result
def cli():
 m=load();count=0
 cases=[({},'cat cat\n猫 cat\n','dog dog\n猫 dog\n'),({'--fixed-strings':True,'find':'.','replace':'$1\\n'},'a.b','a$1\\nb'),({'find':'(cat)','replace':'[$1]'},'cat','[cat]'),({'find':'(?P<word>cat)','replace':'${word}!' },'cat','cat!'),({'find':'cat','replace':''},'cat cat',' '),({'find':'','replace':'_'},'a','_a_'),({'find':'--name','replace':'value'},'--name','value'),({'flag-i':True},'CAT cat','dog dog'),({'flag-c':True},'CAT cat','CAT dog'),({'flag-w':True},'cat scatter cat','dog scatter dog'),({'--max-replacements':'1'},'cat cat\ncat cat\n','dog cat\ndog cat\n'),({'--max-replacements':'1','--across':True},'cat cat\ncat cat\n','dog cat\ncat cat\n'),({'--across':True,'find':'a\nb','replace':'x'},'a\nb\n','x\n'),({'--across':True,'flag-s':True,'find':'a.b','replace':'x'},'a\nb\n','x\n'),({'--across':True,'flag-m':True,'find':'^cat','replace':'x'},'cat\ncat\n','x\nx\n'),({'--across':True,'flag-e':True,'find':'^cat','replace':'x'},'cat\ncat\n','x\ncat\n'),({'replace':'\\n'},'cat','\n'),({},'cat\r\n猫 cat\r\n','dog\r\n猫 dog\r\n')]
 for values,src,expected in cases:
  r=m.process(str(EXE),m.build_sd_args(options(**values)),src.encode(),[],threading.Event());assert r['returncode']==0,(values,r);assert r['stdout']==expected.encode(),(values,r['stdout'],expected);count+=1
 for key,value in [('--max-replacements','-1'),('--max-replacements','x'),('--max-replacements','2147483648'),('find','a\x00b'),('replace','a\x00b')]:
  try:m.build_sd_args(options(**{key:value}));raise AssertionError(key)
  except ValueError:count+=1
 for values in [{'flag-i':True,'flag-c':True},{'flag-e':True,'flag-m':True}]:
  try:m.build_sd_args(options(**values));raise AssertionError(values)
  except ValueError:count+=1
 r=m.process(str(EXE),m.build_sd_args(options(find='[')),b'cat',[],threading.Event());assert r['returncode']!=0;count+=1
 with tempfile.TemporaryDirectory() as td:
  d=Path(td);a=d/'日本語.txt';a.write_bytes('cat cat\n猫 cat\n'.encode());b=d/'二番.txt';b.write_bytes(b'cat');orig={p:p.read_bytes() for p in [a,b]}
  r=m.process(str(EXE),m.build_sd_args(options()),b'',[str(a)],threading.Event());assert r['stdout']=='dog dog\n猫 dog\n'.encode();count+=1
  r=m.process(str(EXE),m.build_sd_args(options()),b'',[str(a),str(b)],threading.Event());assert r['extension']=='.zip';z=zipfile.ZipFile(io.BytesIO(r['stdout']));assert len(z.namelist())==2;assert z.read(z.namelist()[0])=='dog dog\n猫 dog\n'.encode();assert z.read(z.namelist()[1])==b'dog';count+=1
  r=m.process(str(EXE),m.build_sd_args(options(),True),b'',[str(a),str(b)],threading.Event());assert r['extension']=='.txt';assert b'dog' in r['stdout'];count+=1
  for p,data in orig.items():assert p.read_bytes()==data
  dup=d/'sub';dup.mkdir();c=dup/a.name;c.write_bytes(b'cat');r=m.process(str(EXE),m.build_sd_args(options()),b'',[str(a),str(c)],threading.Event());z=zipfile.ZipFile(io.BytesIO(r['stdout']));assert len(set(z.namelist()))==2;count+=1
  invalid=d/'invalid.txt';invalid.write_bytes(b'\xff');big=d/'big.txt';big.write_bytes(b'x'*(2*1024*1024+1))
  for paths in [[str(d)],[str(d/'absent')],[str(a),str(a)],[str(invalid)],[str(big)],[str(a)]*2001]:
   try:m.process(str(EXE),m.build_sd_args(options()),b'',paths,threading.Event());raise AssertionError(paths[:2])
   except ValueError:count+=1
  before=a.read_bytes();r=runtime.execute(EXE,['--','cat','dog',str(a)],mandatory_args=['--preview']);assert r['returncode']==0 and a.read_bytes()==before;count+=1
 event=threading.Event();event.set()
 try:m.process(str(EXE),m.build_sd_args(options()),b'cat',[],event);raise AssertionError('cancel')
 except InterruptedError:count+=1
 for arg in ['--help','--version']:
  r=runtime.execute(EXE,[arg]);assert r['returncode']==0 and r['stdout'];count+=1
 print('PASS real sd CLI and protected batch',count,'checks')
def settle(app):
 limit=time.monotonic()+15
 while time.monotonic()<limit:
  app.root.update();time.sleep(.02)
  if (not app.worker or not app.worker.is_alive()) and app.q.empty() and app.last_result is not None:break
 assert app.last_result and 'stdout' in app.last_result,app.last_result
def gui():
 from unittest.mock import patch
 from PIL import ImageGrab
 m=load();app=m.ReplaceApp(PROFILE,APP);app.exe_path=str(EXE);app.advanced.exe_path=str(EXE)
 try:
  app._demo();app.run();settle(app);assert 'dog' in app.out_text.get('1.0','end')
  d=Path('C:/Users/Public/Documents/kiwi-replace-demo');d.mkdir(parents=True,exist_ok=True);a=d/'サンプル.txt';a.write_bytes(b'cat cat\n');b=d/'別.txt';b.write_bytes('猫 cat'.encode());before=a.read_bytes()
  app.in_text.delete('1.0','end');app.mode_var.set('ファイルを置換');app.paths=[str(a),str(b)];app.path_list.insert('end',str(a),str(b));app.run();settle(app);assert app.last_result['extension']=='.zip'
  saved=d/'result.zip'
  with patch('workbench.filedialog.asksaveasfilename',return_value=str(saved)),patch('workbench.messagebox.askyesno',return_value=True):app._save()
  assert saved.read_bytes()==app.last_result['stdout'];assert a.read_bytes()==before
  app.mode_var.set('ファイルをプレビュー');app.run();settle(app);assert b'dog' in app.last_result['stdout'] and app.last_result['extension']=='.txt';assert a.read_bytes()==before
  app._demo();app.values['--fixed-strings'].set(True);app.values['find'].set('.');app.values['replace'].set('$1');app.in_text.delete('1.0','end');app.in_text.insert('1.0','a.b');app.run();settle(app);assert app.last_result['stdout']==b'a$1b'
  app._demo();app.values['--max-replacements'].set('x')
  with patch.object(m.messagebox,'showerror') as error:app.run();assert error.called
  app._demo();app.run();settle(app);app.root.update();user32=ctypes.windll.user32;user32.GetAncestor.argtypes=[ctypes.c_void_p,ctypes.c_uint];user32.GetAncestor.restype=ctypes.c_void_p
  ImageGrab.grab(window=user32.GetAncestor(app.root.winfo_id(),2)).save(ROOT/'site/assets/screenshots/kiwi-replace-public.png')
  app.advanced.open_window();app.root.update();assert app.advanced.option_tree.get_children();app.advanced._on_toplevel_close();app.root.update()
  app.mode_var.set('バージョン');app.run();settle(app);assert b'1.0.0' in app.last_result['stdout']
  print('PASS native text/file/preview/batch save, invalid option, screenshot, advanced, version')
 finally:app._on_close()
def portable():
 from verify_advanced_zip import windows,wait_window,user32
 from PyInstaller.archive.readers import CArchiveReader
 pin=json.loads((APP/'upstream-pin.json').read_text(encoding='utf8'));pkg=APP/f"{pin['app_exe']}-{pin['version']}-win11-x64.zip"
 with zipfile.ZipFile(pkg) as z,tempfile.TemporaryDirectory() as td:
  assert {'README.txt','LICENSE','UPSTREAM-LICENSE.txt','THIRD-PARTY-NOTICES.txt','Runtime-LICENSES.txt'}<=set(z.namelist());z.extractall(td)
  exe=Path(td)/'KiwiReplace.exe';a=CArchiveReader(str(exe));assert json.loads(a.extract('profile.json'))==PROFILE;assert hashlib.sha256(a.extract('sd.exe')).hexdigest()==pin['binary_sha']
  existing=windows();proc=subprocess.Popen([str(exe)])
  try:
   root=wait_window(PROFILE['title'],existing);sub=user32.GetSubMenu(user32.GetMenu(root),0);user32.PostMessageW(root,0x0111,user32.GetMenuItemID(sub,0),0)
   detail=wait_window('sd.exe - 詳細機能',existing);user32.PostMessageW(detail,0x0010,0,0);time.sleep(.2);user32.PostMessageW(root,0x0010,0,0);proc.wait(timeout=12);assert proc.returncode==0
  finally:
   if proc.poll() is None:subprocess.run(['taskkill','/F','/T','/PID',str(proc.pid)],capture_output=True)
 print('PASS portable ZIP licenses, binary pin, frozen main and advanced GUI, close')
if __name__=='__main__':globals()[sys.argv[1]]()
