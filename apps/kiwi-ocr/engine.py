"""Offline OCR and preview tasks using only verified bundled models."""
import hashlib,importlib.util,json,sys
from pathlib import Path
import images
ROOT=Path(__file__).resolve().parent

def models():
 pin=json.loads((Path(getattr(sys,'_MEIPASS',ROOT))/'upstream-pin.json').read_text(encoding='utf8'))
 root=Path(sys._MEIPASS)/'rapidocr/models' if getattr(sys,'frozen',False) else Path(importlib.util.find_spec('rapidocr').origin).parent/'models'
 out={}
 for key,info in pin['models'].items():
  path=root/info['name']
  if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest()!=info['sha256']:raise ValueError('同梱モデルの検証に失敗しました。配布ZIPを展開し直してください。')
  out[key]=str(path)
 return out

def execute(task):
 if not isinstance(task,dict) or task.get('op') not in ('preview','ocr','annotate'):raise ValueError('使えない操作です。')
 path=task['path'];rotation=task.get('rotation',0);region=task.get('region');im,meta=images.load(path,rotation,region)
 if task['op']=='preview':return {**meta,'preview':images.preview(im)}
 if task['op']=='annotate':
  previous=task['result']
  if meta['source_sha256']!=previous['source_sha256']:raise ValueError('元画像が変更されています。もう一度読み取ってください。')
  return {'png':images.encode(images.annotate(im,previous['rows']))}
 from bootstrap import prepare
 prepare()
 from backend import recognize
 result=recognize(im,task.get('mode','full'),task.get('opts',{}),models())
 return {**result,**meta,'options':task.get('opts',{}),'path':path,'mode':task.get('mode','full'),'preview':images.preview(im),'task':{k:task[k] for k in ('path','rotation','region') if k in task}}
