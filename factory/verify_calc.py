import ctypes,hashlib,importlib.util,json,subprocess,sys,tempfile,time,zipfile,tomllib,threading
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];APP=ROOT/'apps/kiwi-calc'
PIN=json.loads((APP/'upstream-pin.json').read_text(encoding='utf8'))
EXE=ROOT/'data/numbat/official'/PIN['archive_member'];PROFILE=json.loads((APP/'profile.json').read_text(encoding='utf8'))
sys.path.insert(0,str(ROOT/'apps/common'));sys.path.insert(0,str(APP))
import runtime
def load():
 spec=importlib.util.spec_from_file_location('kiwi_calc',APP/'main.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
def defaults():return {f['flag']:f['default'] for f in PROFILE['fields']}
def cli():
 m=load();v=defaults();count=0
 def job(mode,text='',paths=None,**changes):
  vals=dict(v);vals.update(changes);return m.run_job(EXE,vals,mode,text,paths or [],threading.Event())
 def ok(r,part):assert r['returncode']==0 and part.encode() in r['stdout'],r
 for n,src,tgt,part in [('1','km','m','1000 m'),('100','km/h','m/s','27.7778 m/s'),('-5','m','cm','-500 cm'),('25','°C','°F','77'),('1','GiB','MiB','1024')]:
  ok(job('単位変換',number=n,source=src,target=tgt),part);count+=1
 for code in m.SAMPLES.values():
  r=job('連続入力・REPLコマンド' if code.startswith('list units') else 'プログラム',code);assert r['returncode']==0 and not r['stderr'],r;count+=1
 ok(job('プログラム','let x = 5\nprint(x*2)'), '10')
 ok(job('プログラム','let x = 5',expressions='print(x*2)\nprint(x*4)'), '20')
 ok(job('プログラム','let x = 5',**{'--inspect-interactively':True,'repl_commands':'print(x*3)\nquit'}),'15')
 assert job('プログラム','1 m + 1 s')['returncode']!=0
 assert job('プログラム','let = 5')['returncode']!=0
 ok(job('プログラム','#'+'a'*40000+'\n1+2'),'3')
 count+=6
 for key,choices in [('--pretty-print',['always','never','auto']),('--color',['always','never','auto']),('--intro-banner',['long','short','off'])]:
  for choice in choices:ok(job('プログラム','1+2',**{key:choice}),'3');count+=1
 ok(job('プログラム','1+2',**{'--no-prelude':True}),'3')
 ok(job('プログラム','1+2',**{'--debug':True,'--no-prelude':True}),'3')
 ok(job('プログラム','1+2',**{'--no-config':False,'--no-init':True}),'3')
 ok(job('単位変換',**{'--inspect-interactively':True,'repl_commands':'print(7)\nquit'}),'7');count+=4
 with tempfile.TemporaryDirectory() as td:
  p=Path(td)/'日本語スクリプト.nbt';p.write_text('let x=5\nprint(args())',encoding='utf8');before=p.read_bytes()
  r=job('スクリプト',paths=[str(p)],script_args='hello world\n--flag',expressions='print(x*2)',**{'--inspect-interactively':True,'repl_commands':'print(x*3)\nquit'})
  ok(r,'hello world');ok(r,'--flag');ok(r,'10');ok(r,'15');assert p.read_bytes()==before;count+=1
 for changes in [dict(number='nan'),dict(number='inf'),dict(source='m\ns'),dict(target='m\rs'),dict(number='1\x00')]:
  try:job('単位変換',**changes);raise AssertionError(changes)
  except ValueError:count+=1
 for mode,text,paths,changes in [('プログラム','',[],{}),('プログラム','a'*(2*1024*1024+1),[],{}),('連続入力・REPLコマンド',' ',[],{}),('スクリプト','',[],{}),('スクリプト','',['C:/missing.nbt'],{}),('プログラム','1',[],{'expressions':'1'*12001}),('プログラム','1',[],{'script_args':'x'*31000}),('プログラム','1',[],{'--color':'wrong'}),('プログラム','1',[],{'--debug':True})]:
  try:job(mode,text,paths,**changes);raise AssertionError(mode)
  except (ValueError,FileNotFoundError):count+=1
 ok(job('ヘルプ','x'*(2*1024*1024+1)), 'Usage:')
 ok(job('バージョン'),'1.24.0');count+=2
 assert '--no-config' not in m.build_options({'--no-config':False,'--inspect-interactively':True})
 assert '--inspect-interactively' in m.build_options({'--inspect-interactively':True})
 assert tomllib.loads(m.CONFIG_TEMPLATE)['formatting']['datetime']=='%Y-%m-%d %H:%M:%S'
 try:runtime.build_command(EXE,['--generate-config'],blocked_flags=['--generate-config']);raise AssertionError
 except ValueError:pass
 cancel=threading.Event();cancel.set()
 try:m.run_job(EXE,v,'プログラム','1+2',[],cancel);raise AssertionError
 except InterruptedError:pass
 print('PASS Numbat CLI/core',count,'checks, all sample programs, input validation, args, config, cancel')
def settle(app):
 deadline=time.monotonic()+40
 while time.monotonic()<deadline:
  app.root.update();time.sleep(.03)
  if app.worker and not app.worker.is_alive() and app.q.empty() and app.last_result is not None:break
 assert app.last_result and 'stdout' in app.last_result,app.last_result
def gui():
 from PIL import ImageGrab
 from unittest.mock import patch
 m=load();app=m.CalcApp(PROFILE,APP);app.exe_path=str(EXE);app.advanced.exe_path=str(EXE)
 demo=Path('C:/Users/Public/Documents/kiwi-calc-demo');demo.mkdir(parents=True,exist_ok=True)
 try:
  app.run();settle(app);assert b'1000 m' in app.last_result['stdout']
  app.sample_var.set('変数と関数');app._sample();app.run();settle(app);assert b'16.0 km/h' in app.last_result['stdout']
  app.values['--color'].set('always');app.run();settle(app);assert any(t.startswith('glow_') for t in app.out_text.tag_names())
  out=demo/'result.txt'
  with patch('workbench.filedialog.asksaveasfilename',return_value=str(out)),patch('workbench.messagebox.askyesno',return_value=True):app._save()
  assert out.read_bytes()==app.last_result['stdout']
  script=demo/'sample.nbt'
  with patch.object(m.filedialog,'asksaveasfilename',return_value=str(script)),patch.object(m.messagebox,'askyesno',return_value=True):app._save_program()
  assert script.read_bytes()==app.in_text.get('1.0','end-1c').encode()
  app.mode_var.set('スクリプト');app.paths=[str(script)];before=script.read_bytes();app.run();settle(app);assert before==script.read_bytes()
  app._config();config=demo/'config.toml'
  with patch('workbench.filedialog.asksaveasfilename',return_value=str(config)),patch('workbench.messagebox.askyesno',return_value=True):app._save()
  assert tomllib.loads(config.read_text())['exchange-rates']['fetching-policy']=='on-startup'
  app.sample_var.set('変数と関数');app._sample();app.run();settle(app);app.root.update()
  u=ctypes.windll.user32;u.GetAncestor.argtypes=[ctypes.c_void_p,ctypes.c_uint];u.GetAncestor.restype=ctypes.c_void_p
  ImageGrab.grab(window=u.GetAncestor(app.root.winfo_id(),2)).save(ROOT/'site/assets/screenshots/kiwi-calc-public.png')
  app.advanced.open_window();app.root.update();assert app.advanced.option_tree.get_children();app.advanced._on_toplevel_close();app.root.update()
  app.mode_var.set('バージョン');app.run();settle(app);assert b'1.24.0' in app.last_result['stdout']
  print('PASS actual GUI conversion/program/script, color, result/script/config save, public screenshot, advanced, version')
 finally:app._on_close()
def portable():
 from verify_advanced_zip import windows,wait_window,user32
 from PyInstaller.archive.readers import CArchiveReader
 pkg=APP/'KiwiCalc-0.1.0-win11-x64.zip'
 with zipfile.ZipFile(pkg) as z,tempfile.TemporaryDirectory() as td:
  assert {'README.txt','LICENSE','UPSTREAM-LICENSE.txt','THIRD-PARTY-NOTICES.txt','Runtime-LICENSES.txt'}<=set(z.namelist());z.extractall(td)
  exe=Path(td)/'KiwiCalc.exe';a=CArchiveReader(str(exe));assert json.loads(a.extract('profile.json'))==PROFILE;assert hashlib.sha256(a.extract('numbat.exe')).hexdigest()==PIN['binary_sha']
  existing=windows();proc=subprocess.Popen([str(exe)])
  try:
   root=wait_window(PROFILE['title'],existing);sub=user32.GetSubMenu(user32.GetMenu(root),0);user32.PostMessageW(root,0x0111,user32.GetMenuItemID(sub,0),0)
   detail=wait_window('numbat.exe - 詳細機能',existing);user32.PostMessageW(detail,0x0010,0,0);time.sleep(.2);user32.PostMessageW(root,0x0010,0,0);proc.wait(timeout=12);assert proc.returncode==0
  finally:
   if proc.poll() is None:subprocess.run(['taskkill','/F','/T','/PID',str(proc.pid)],capture_output=True)
 print('PASS portable ZIP license files, pinned binary, main and detail windows, clean exit')
if __name__=='__main__':globals()[sys.argv[1]]()
