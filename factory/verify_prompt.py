import ctypes,hashlib,importlib.util,json,os,subprocess,sys,tempfile,time,zipfile,threading
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];APP=ROOT/'apps/kiwi-prompt';EXE=ROOT/'data/code2prompt/code2prompt-x86_64-pc-windows-msvc.exe'
PROFILE=json.loads((APP/'profile.json').read_text(encoding='utf8'))
sys.path.insert(0,str(ROOT/'apps/common'));sys.path.insert(0,str(APP))
import runtime
from workbench import build_args
def load():
 spec=importlib.util.spec_from_file_location('kiwi_prompt',APP/'main.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
def cli():
 m=load();n=0;mode=PROFILE['modes'][0];defaults={f['flag']:f['default'] for f in PROFILE['fields']}
 with tempfile.TemporaryDirectory() as td:
  p=Path(td);(p/'hello.py').write_text('print("hello")\n',encoding='utf8');(p/'skip.txt').write_text('ignore me',encoding='utf8');(p/'hidden.py').write_text('hidden',encoding='utf8')
  (p/'.gitignore').write_text('hidden.py\n',encoding='utf8')
  def git(*args):subprocess.run(['git','-C',str(p),*args],check=True,capture_output=True)
  git('init','-b','main');git('add','.');git('-c','user.name=Demo','-c','user.email=demo@example.invalid','commit','-m','base-demo')
  git('checkout','-b','feature');(p/'hello.py').write_text('print("feature")\n',encoding='utf8');git('add','hello.py');git('-c','user.name=Demo','-c','user.email=demo@example.invalid','commit','-m','feature-demo')
  before=(p/'hello.py').read_bytes();(p/'hello.py').write_bytes(before+b'# pending\n');baseline=(p/'hello.py').read_bytes()
  def run(**changes):
   values=dict(defaults);values.update(changes);args=build_args(PROFILE,values,mode['label'],[str(p)])
   r=m.process(EXE,args,None,mode,threading.Event());assert r['returncode']==0,(r['returncode'],r['stderr'][-1200:]);return r
  r=run();assert b'feature' in r['stdout'] and b'Token count:' in r['stderr'];n+=1
  for key,choices in [('--output-format',['markdown','json','xml']),('--encoding',['cl100k','p50k','p50k_edit','r50k']),('--token-format',['raw','format']),('--sort',['name_asc','name_desc','date_asc','date_desc'])]:
   for choice in choices:
    r=run(**{key:choice});assert r['stdout'];n+=1
    if key=='--output-format' and choice=='json':json.loads(r['stdout'])
  for flag in ['--full-directory-tree','--line-numbers','--absolute-paths','--follow-symlinks','--hidden','--no-codeblock','--no-ignore','--quiet','--diff','--token-map']:
   r=run(**{flag:True});assert r['stdout'];n+=1
   if flag=='--quiet':assert b'Token count:' not in r['stderr']
   if flag=='--token-map':assert b'hello.py' in r['stderr']
  r=run(**{'--include':'*.py','--exclude':'hidden.py'});assert b'feature' in r['stdout'] and b'ignore me' not in r['stdout'];n+=1
  r=run(**{'--diff-from':'main','--diff-to':'feature','--log-from':'main','--log-to':'feature'});assert b'feature-demo' in r['stdout'] and b'Git Branch Diff:' in r['stdout'] and b'print("hello")' in r['stdout'] and b'print("feature")' in r['stdout'];n+=1
  for fmt in ['xml','json']:
   r=run(**{'--output-format':fmt,'--diff-from':'main','--diff-to':'feature','--log-from':'main','--log-to':'feature'})
   payload=json.loads(r['stdout'])['prompt'] if fmt=='json' else r['stdout'].decode();assert 'feature-demo' in payload and '<git-branch-diff>' in payload;n+=1
  template=p/'custom.hbs';template.write_text('CUSTOM {{absolute_code_path}} {{task}}',encoding='utf8');assert b'Review {{literal}}' in run(**{'--template':str(template),'--template-vars':json.dumps({'task':'Review {{literal}}'})})['stdout'];n+=1
  try:run(**{'--template':str(template)});raise AssertionError('missing template variable should not launch terminal prompt')
  except ValueError:n+=1
  config=p/'.c2pconfig';config.write_text('[user_variables]\ntask="configured task"\n',encoding='utf8');config_before=config.read_bytes()
  assert b'configured task' in run(**{'--template':str(template)})['stdout'];assert config.read_bytes()==config_before;n+=1
  template.write_text('{{#if task}}CUSTOM {{task}}{{else}}EMPTY{{/if}}',encoding='utf8');assert b'EMPTY' in run(**{'--template':str(template),'--template-vars':'{"task":""}'})['stdout'];n+=1
  r=run(**{'--output-format':'json','--token-map':True,'--token-map-lines':'2','--token-map-min-percent':'1'});json.loads(r['stdout']);assert r['stderr'];n+=1
  assert (p/'hello.py').read_bytes()==baseline
  original=['--quiet','--diff-from','main','--diff-to','feature','--',str(p)];copy=list(original)
  assert m.normalize_branch_args(original)==['--quiet','--git-diff-branch','main','feature','--',str(p)] and original==copy
  assert m.normalize_branch_args(['--','--diff-from','main'])==['--','--diff-from','main']
  for args in [['--log-from','main','--',str(p)],['--diff-from','a','--diff-from','b'],['--diff-to'],['--log-to',''],['--','missing'],['--',str(p),str(p)],['--tui','--',str(p)]]:
   try:m.process(EXE,args,None,mode,threading.Event());raise AssertionError(args)
   except ValueError:n+=1
 for flag in ['--help','--version']:
  r=m.process(EXE,[flag],None,{},threading.Event());assert r['returncode']==0 and r['stdout'];n+=1
 print('PASS code2prompt real CLI',n,'checks, filters, formats, counts/map, real Git diffs/log, template, immutable inputs')
def settle(a):
 end=time.monotonic()+20
 while time.monotonic()<end:
  a.root.update();time.sleep(.03)
  if (not a.worker or not a.worker.is_alive()) and a.q.empty() and a.last_result is not None:break
 assert a.last_result and 'stdout' in a.last_result,a.last_result
def gui():
 from PIL import ImageGrab
 from unittest.mock import patch
 m=load();a=m.PromptApp(PROFILE,APP);a.exe_path=str(EXE);a.advanced.exe_path=str(EXE)
 try:
  a._demo();a.values['--output-format'].set('json');a.values['--token-map'].set(True);a.run();settle(a);json.loads(a.last_result['stdout'])
  a._copy();assert a.root.clipboard_get()==a.last_result['stdout'].decode()
  demo=Path(a.paths[0]);out=demo/'saved.json';log=demo/'saved.log'
  with patch('workbench.filedialog.asksaveasfilename',return_value=str(out)),patch('workbench.messagebox.askyesno',return_value=True):a._save()
  with patch.object(m.filedialog,'asksaveasfilename',return_value=str(log)),patch.object(m.messagebox,'askyesno',return_value=True):a._save_diagnostics()
  assert out.read_bytes()==a.last_result['stdout'];assert log.read_bytes()==a.last_result['stderr']
  a._demo();a.repeat_widgets['--include'].insert('1.0','*.py');a.values['--quiet'].set(True);a.run();settle(a);assert b'hello.py' in a.last_result['stdout'] and b'A tiny example' not in a.last_result['stdout']
  a.root.update();u=ctypes.windll.user32;u.GetAncestor.argtypes=[ctypes.c_void_p,ctypes.c_uint];u.GetAncestor.restype=ctypes.c_void_p
  ImageGrab.grab(window=u.GetAncestor(a.root.winfo_id(),2)).save(ROOT/'site/assets/screenshots/kiwi-prompt-public.png')
  a.advanced.open_window();a.root.update();assert a.advanced.option_tree.get_children();a.advanced._on_toplevel_close();a.root.update()
  a.mode_var.set('バージョン');a.run();settle(a);assert b'4.2.0' in a.last_result['stdout']
  print('PASS actual GUI generation/JSON/filter/clipboard/save/diagnostics, screenshot, advanced, version')
 finally:a._on_close()
def portable():
 from verify_advanced_zip import windows,wait_window,user32
 from PyInstaller.archive.readers import CArchiveReader
 pin=json.loads((APP/'upstream-pin.json').read_text(encoding='utf8'));pkg=APP/'KiwiPrompt-0.1.0-win11-x64.zip'
 with zipfile.ZipFile(pkg) as z,tempfile.TemporaryDirectory() as td:
  assert {'README.txt','LICENSE','UPSTREAM-LICENSE.txt','THIRD-PARTY-NOTICES.txt','Runtime-LICENSES.txt'}<=set(z.namelist());z.extractall(td)
  exe=Path(td)/'KiwiPrompt.exe';a=CArchiveReader(str(exe));assert json.loads(a.extract('profile.json'))==PROFILE;assert hashlib.sha256(a.extract('code2prompt.exe')).hexdigest()==pin['binary_sha']
  assert any(k.casefold().endswith('vcruntime140.dll') for k in a.toc),'Microsoft runtime dependency not bundled'
  existing=windows();proc=subprocess.Popen([str(exe)])
  try:
   hwnd=wait_window(PROFILE['title'],existing);sub=user32.GetSubMenu(user32.GetMenu(hwnd),0);user32.PostMessageW(hwnd,0x0111,user32.GetMenuItemID(sub,0),0)
   detail=wait_window('code2prompt.exe - 詳細機能',existing);user32.PostMessageW(detail,0x0010,0,0);time.sleep(.2);user32.PostMessageW(hwnd,0x0010,0,0);proc.wait(timeout=12);assert proc.returncode==0
  finally:
   if proc.poll() is None:subprocess.run(['taskkill','/F','/T','/PID',str(proc.pid)],capture_output=True)
 print('PASS portable ZIP notices, pinned binary and VCRUNTIME, normal/detail windows, exit')
if __name__=='__main__':globals()[sys.argv[1]]()
