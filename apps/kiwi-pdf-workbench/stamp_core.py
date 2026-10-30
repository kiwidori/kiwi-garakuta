"""Add visible PDF marks in an isolated, offline native process."""
import ctypes,json,math,re,sys,tempfile
from pathlib import Path
from consumer_runtime import Engine,stage,save_file,check
ROOT=Path(sys.executable).parent if getattr(sys,'frozen',False) else Path(__file__).resolve().parent
ROOT=ROOT/'stamp-engine'
ENGINE=Engine(ROOT)
POSITIONS={'左上':'tl','上':'tc','右上':'tr','左':'l','中央':'c','右':'r','左下':'bl','下':'bc','右下':'br'}
BASE=['--conf','disable','--offline']

def number(value,low,high):
 try:n=float(value)
 except (TypeError,ValueError):raise ValueError('数値の設定を確認してください。')
 if not math.isfinite(n) or not low<=n<=high:raise ValueError(f'数値は{low}～{high}で指定してください。')
 return n

def pages(value,count):
 value=value.strip().replace(' ','')
 if value in {'','all'}:return ''
 if value in {'odd','even'}:
  if value=='even' and count<2:raise ValueError('偶数ページがありません。')
  return value
 if len(value)>1000:raise ValueError('ページ指定が長すぎます。')
 for part in value.split(','):
  if not re.fullmatch(r'[1-9]\d{0,3}(?:-[1-9]\d{0,3})?',part):raise ValueError('ページは1-3,5、odd、even、または空欄にしてください。')
  ends=list(map(int,part.split('-')))
  if ends[0]>ends[-1] or ends[-1]>count:raise ValueError(f'昇順、PDFのページ数（{count}）以内で指定してください。')
 return value

def info(path,work,cancel):
 raw=ENGINE.call(['info',*BASE,'--json',str(path)],work,cancel,timeout=30,cap=128*1024**2)
 # Native info diagnostics go to stderr, JSON to stdout.
 value=json.loads(raw)['infos'][0]
 if type(value.get('pageCount')) is not int or not 1<=value['pageCount']<=1000:raise ValueError('1～1000ページのPDFを選んでください。')
 if value.get('encrypted') or value.get('signatures'):raise ValueError('暗号化・電子署名付きPDFは対象外です。解除や署名の保持は行いません。')
 return value

def description(v):
 if v['position'] not in POSITIONS:raise ValueError('位置を選んでください。')
 if len(v.get('extra','{}'))>4096:raise ValueError('詳細設定は4096文字までです。')
 try:extra=json.loads(v.get('extra','{}'))
 except (ValueError,TypeError):raise ValueError('詳細設定はJSONオブジェクトにしてください。')
 if not isinstance(extra,dict):raise ValueError('詳細設定はJSONオブジェクトにしてください。')
 scale_mode=extra.get('scale_mode','rel')
 if scale_mode not in ('abs','rel'):raise ValueError('scale_modeはabsまたはrelです。')
 scale=number(v['scale'],.01,100 if scale_mode=='abs' else 1);rotation=number(v['rotation'],-180,180);opacity=number(v['opacity'],.01,1)
 desc={'position':POSITIONS[v['position']],'scalefactor':f'{scale} {scale_mode}','rotation':str(rotation),'opacity':str(opacity)}
 for key,val in extra.items():
  if key=='scale_mode':continue
  if key=='diagonal':
   if type(val) is not int or val not in {1,2}:raise ValueError('diagonalは1または2です。')
   desc.pop('rotation',None);desc[key]=str(val)
  elif key in {'offset','margins'}:
   count=2 if key=='offset' else 4
   if not isinstance(val,list) or len(val) not in ({2} if key=='offset' else {1,2,3,4}):raise ValueError('offsetは2個、marginsは1～4個の数値配列です。')
   desc[key]=' '.join(str(number(x,-1000 if key=='offset' else 0,1000)) for x in val)
  elif key in {'fillcolor','strokecolor','backgroundcolor'}:
   if not isinstance(val,str) or not re.fullmatch(r'#[0-9a-fA-F]{6}',val):raise ValueError('色は#336699の形式です。')
   desc[key]=val
  elif key=='points':
   points=number(val,1,300)
   if not points.is_integer():raise ValueError('pointsは整数です。')
   desc[key]=str(int(points))
  elif key=='rendermode':
   if type(val) is not int or val not in {0,1,2}:raise ValueError('rendermodeは0、1、2です。')
   desc[key]=str(val)
  elif key=='aligntext':
   if val not in {'l','c','r','j'}:raise ValueError('aligntextはl、c、r、jです。')
   desc[key]=val
  elif key=='fontname':
   if not isinstance(val,str) or val not in {'Helvetica','Helvetica-Bold','Helvetica-Oblique','Helvetica-BoldOblique','Times-Roman','Times-Bold','Times-Italic','Times-BoldItalic','Courier','Courier-Bold','Courier-Oblique','Courier-BoldOblique','Symbol','ZapfDingbats'}:raise ValueError('PDF標準14フォントから選んでください。')
   desc[key]=val
  elif key=='border':
   if isinstance(val,dict):
    if set(val)-{'width','round','color'}:raise ValueError('borderの項目はwidth、round、colorです。')
    if type(val.get('round',False)) is not bool:raise ValueError('border.roundはtrueかfalseです。')
    color=val.get('color','#808080')
    if not isinstance(color,str) or not re.fullmatch(r'#[0-9a-fA-F]{6}',color):raise ValueError('border.colorは#336699の形式です。')
    desc[key]=str(number(val.get('width',1),.01,100))+(' round' if val.get('round') else '')+' '+color
   else:desc[key]=str(number(val,0,100))
  else:raise ValueError('未対応の詳細設定: '+str(key))
 return ', '.join(k+':'+s for k,s in desc.items())

def raster_text(text,work):
 from PIL import Image,ImageDraw,ImageFont
 if not text.strip() or len(text)>200 or len(text.splitlines())>4 or any(ord(c)<32 and c!='\n' for c in text):raise ValueError('日本語の文字は200文字・4行までです。')
 buffer=ctypes.create_unicode_buffer(32768)
 windows=ctypes.WinDLL('kernel32',use_last_error=True).GetWindowsDirectoryW
 windows.argtypes=[ctypes.c_wchar_p,ctypes.c_uint];windows.restype=ctypes.c_uint
 length=windows(buffer,len(buffer))
 if not 0<length<len(buffer):raise OSError('Windowsのフォルダーを取得できません。')
 fontpath=Path(buffer.value)/'Fonts/YuGothM.ttc'
 if not fontpath.is_file():raise ValueError('Windowsの游ゴシックがありません。日本語入りPNG画像を代わりに指定してください。')
 font=ImageFont.truetype(str(fontpath),80)
 box=ImageDraw.Draw(Image.new('RGBA',(1,1))).multiline_textbbox((0,0),text,font=font,spacing=16)
 w,h=box[2]-box[0]+32,box[3]-box[1]+32
 if w>12000 or h>2000:raise ValueError('文字画像が大きすぎます。改行して短くしてください。')
 im=Image.new('RGBA',(w,h),(255,255,255,0));ImageDraw.Draw(im).multiline_text((16-box[0],16-box[1]),text,font=font,fill=(100,100,100,255),spacing=16)
 path=work/'text.png';im.save(path);return path

def run(v,folder,cancel):
 check(cancel)
 if v['layer'] not in {'手前（スタンプ）','背面（透かし）'} or v['action'] not in {'追加','更新','削除'}:raise ValueError('重ね方と操作を選んでください。')
 kind=v['kind'];allowed={'日本語の文字（画像化）','欧文・ページ番号','画像','PDFの指定ページ','PDFを順番に重ねる'}
 if kind not in allowed:raise ValueError('重ねる内容を選んでください。')
 with tempfile.TemporaryDirectory(prefix='kiwi-pdf-stamp-') as td:
  work=Path(td);source=stage(v['input'],work,cancel,{'.pdf'},limit=32*1024**2);data=info(source,work,cancel);selection=pages(v['pages'],data['pageCount'])
  args=['stamp' if v['layer']=='手前（スタンプ）' else 'watermark',{'追加':'add','更新':'update','削除':'remove'}[v['action']],*BASE]
  if selection:args+=['--pages',selection]
  out=work/'output.pdf'
  if v['action']=='削除':args+=['--',str(source),str(out)]
  else:
   desc=description(v)
   if kind=='欧文・ページ番号':
    text=v['text']
    if not text.strip() or len(text)>500 or any((ord(c)<32 and c!='\n') or ord(c)>126 for c in text):raise ValueError('欧文モードは半角英数字・記号500文字までです。日本語は画像化モードをご利用ください。')
    mode='text';mark=text
   elif kind=='日本語の文字（画像化）':
    mode='image';mark=str(raster_text(v['text'],work))
    if json.loads(v.get('extra','{}')):raise ValueError('日本語画像化では詳細設定は使えません。位置・幅・回転・濃さを指定してください。')
   else:
    markdir=work/'mark';markdir.mkdir()
    mark=stage(v['mark'],markdir,cancel,{'.png','.jpg','.jpeg','.webp','.tif','.tiff'} if kind=='画像' else {'.pdf'},limit=16*1024**2)
    mode='image' if kind=='画像' else 'pdf'
    if mode=='pdf':
     other=info(mark,markdir,cancel)
     # pdfcpu uses ':' to separate the page selector; avoid a Windows drive prefix.
     mark=mark.relative_to(work).as_posix()
     if kind=='PDFの指定ページ':
      page=int(v['markpage'])
      if not 1<=page<=other['pageCount']:raise ValueError('重ねるPDFのページ番号を確認してください。')
      mark=str(mark)+':'+str(page)
     elif ':' in v['markpage']:
      parts=v['markpage'].strip().split(':')
      if len(parts)!=2 or any(not re.fullmatch(r'[1-9]\d{0,3}',part) for part in parts):raise ValueError('順番の開始は「重ねるPDFの開始ページ:元PDFの開始ページ」で指定してください。例: 2:3')
      start,end=map(int,parts)
      if start>other['pageCount'] or end>data['pageCount']:raise ValueError('開始ページがPDFのページ数を超えています。')
      mark=str(mark)+':'+str(start)+':'+str(end)
     elif v['markpage'].strip() and not re.fullmatch(r'[1-9]\d{0,3}',v['markpage'].strip()):raise ValueError('順番の開始を指定する場合は2:3のように指定してください。')
    else:
     from PIL import Image
     with Image.open(mark) as im:
      if im.width*im.height>20_000_000:raise ValueError('画像は2,000万画素までです。')
      if getattr(im,'n_frames',1)!=1:raise ValueError('複数フレーム画像は対象外です。')
   args+=['--mode',mode,'--',str(mark),desc,str(source),str(out)]
  ENGINE.call(args,work,cancel,timeout=180,cap=128*1024**2)
  if not out.is_file() or not 0<out.stat().st_size<=64*1024**2:raise ValueError('PDFの出力を確認できません。')
  result=info(out,work,cancel)
  if result['pageCount']!=data['pageCount']:raise ValueError('出力ページ数が一致しません。')
  ENGINE.call(['validate',*BASE,str(out)],work,cancel,timeout=30,cap=128*1024**2)
  saved=save_file(out,folder,Path(v['input']).stem+'_marked','.pdf',cancel)
  return {'path':str(saved),'pages':result['pageCount'],'bytes':saved.stat().st_size}

def version(cancel):
 with tempfile.TemporaryDirectory(prefix='kiwi-pdf-stamp-info-') as td:return ENGINE.call(['version',*BASE],Path(td),cancel,timeout=10).decode('utf8','replace')
