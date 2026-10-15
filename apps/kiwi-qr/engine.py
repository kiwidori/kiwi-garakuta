"""Bounded barcode operations; no network or automatic file opening."""
import base64,io,json,re
from pathlib import Path
from PIL import Image,ImageOps
import zxingcpp as zx
from qr_make import make_qr
FORMATS=('Code128','Code39','Code39Ext','Code93','Codabar','Code32','PZN','ITF','ITF14','EAN13','EAN8','EAN5','EAN2','ISBN','UPCA','UPCE','DataBar','DataBarStk','DataBarLtd','DataBarExp','DataBarExpStk','Telepen','TelepenNumeric','DXFilmEdge','PDF417','CompactPDF417','MicroPDF417','Aztec','AztecRune','MicroQRCode','RMQRCode','DataMatrix','MaxiCode')
IMAGE_FORMATS=('PNG','JPEG','GIF','BMP','WEBP','TIFF')
Image.MAX_IMAGE_PIXELS=20_000_000

def string(s,limit=3000,empty=False):
 if not isinstance(s,str) or (not s and not empty) or '\0' in s or len(s.encode('utf8'))>limit:raise ValueError('入力内容が空か長すぎます。')
 return s

def integer(n,lo,hi):
 if type(n)!=int or not lo<=n<=hi:raise ValueError('数値の範囲を確認してください。')
 return n

def image_file(path,max_bytes=25*1024*1024,max_pixels=20_000_000):
 p=Path(path)
 if not p.is_absolute() or not p.is_file() or p.stat().st_size>max_bytes:raise ValueError('通常の画像ファイル（25 MiB以下）を選んでください。')
 with Image.open(p) as im:
  if im.format not in IMAGE_FORMATS or im.width*im.height>max_pixels:raise ValueError('対応形式と画像の画素数を確認してください。')
  im.seek(0);im.load();im=ImageOps.exif_transpose(im)
  result=Image.new('RGB',im.size,'white')
  if im.mode=='RGBA':result.paste(im,mask=im.getchannel('A'))
  else:result.paste(im.convert('RGB'))
  return result

def png_bytes(im):
 b=io.BytesIO();im.save(b,format='PNG')
 if b.tell()>4*1024*1024:raise ValueError('画像出力が4 MiBを超えました。')
 return base64.b64encode(b.getvalue()).decode('ascii')

def barcode(text,kind,opts):
 string(text)
 if kind not in FORMATS or not isinstance(opts,dict):raise ValueError('バーコード形式を確認してください。')
 kwargs={};scale=integer(opts.get('scale',3),1,10);hrt=opts.get('hrt',True)
 if type(hrt)!=bool:raise ValueError('hrtはtrue/falseです。')
 for k,v in opts.items():
  if k in ('scale','hrt'):continue
  if k in ('gs1','reader_init','force_square'):
   if type(v)!=bool:raise ValueError(k+'はtrue/falseです。')
  elif k in ('columns','rows','version'):integer(v,1,200)
  elif k=='data_mask':integer(v,0,7)
  elif k in ('ec_level','eci'):
   if not isinstance(v,(str,int)) or type(v)==bool:raise ValueError(k+'の値を確認してください。')
   v=str(v)
   if not re.fullmatch(r'[A-Za-z0-9%_. -]{1,64}',v):raise ValueError(k+'の値を確認してください。')
  else:raise ValueError('使えない設定：'+str(k))
  kwargs[k]=v
 try:b=zx.create_barcode(text,getattr(zx.BarcodeFormat,kind),**kwargs)
 except ValueError as e:raise ValueError('この形式では作成できない内容・設定です。 '+str(e)) from e
 if not b.valid:raise ValueError('この形式で作成できない内容です。')
 pos=b.position;points=(pos.top_left,pos.top_right,pos.bottom_right,pos.bottom_left)
 bound_w=(max(p.x for p in points)-min(p.x for p in points)+65)*scale;bound_h=(max(p.y for p in points)-min(p.y for p in points)+65)*scale
 if max(bound_w,bound_h)>8192 or bound_w*bound_h>4_000_000:raise ValueError('画像が大きすぎます。内容や倍率を減らしてください。')
 view=memoryview(zx.write_barcode_to_image(b,scale=scale,add_hrt=hrt,add_quiet_zones=True));h,w=view.shape[:2]
 if w*h>4_000_000 or max(w,h)>8192:raise ValueError('画像が大きすぎます。内容や倍率を減らしてください。')
 im=Image.frombytes('L',(w,h),view.tobytes())
 decoded=zx.read_barcodes(im,text_mode=zx.TextMode.Plain)
 if not any(x.valid and x.bytes==b.bytes for x in decoded):raise ValueError('作成画像を読み戻せませんでした。形式・倍率・内容を変えてください。')
 return {'png':png_bytes(im),'svg':zx.write_barcode_to_svg(b,scale=scale,add_hrt=hrt,add_quiet_zones=True),'text':b.text,'size':[w,h],'version':0,'format':kind}

def decode(paths,opts):
 if not isinstance(paths,list) or not 1<=len(paths)<=32 or not isinstance(opts,dict):raise ValueError('画像は1～32件です。')
 allowed=('formats','try_rotate','try_downscale','try_invert','text_mode','binarizer','is_pure','ean_add_on_symbol','return_errors');kw={}
 for k,v in opts.items():
  if k not in allowed:raise ValueError('使えない設定：'+str(k))
  if k=='formats':
   if not isinstance(v,list) or not 1<=len(v)<=32:raise ValueError('formatsは形式名の配列です。')
   f=zx.BarcodeFormat.NONE
   for name in v:
    if name not in ('QRCode',*FORMATS):raise ValueError('読み取る形式を確認してください。')
    f=f|getattr(zx.BarcodeFormat,name)
   kw[k]=f
  elif k in ('text_mode','binarizer','ean_add_on_symbol'):
   enum={'text_mode':zx.TextMode,'binarizer':zx.Binarizer,'ean_add_on_symbol':zx.EanAddOnSymbol}[k]
   if not isinstance(v,str) or v not in enum.__members__:raise ValueError(k+'の値を確認してください。')
   kw[k]=getattr(enum,v)
  else:
   if type(v)!=bool:raise ValueError(k+'はtrue/falseです。')
   kw[k]=v
 kw.setdefault('text_mode',zx.TextMode.Plain);rows=[];preview=''
 for path in paths:
  im=image_file(path)
  if not preview:
   thumb=im.copy();thumb.thumbnail((480,360));preview=png_bytes(thumb)
  found=zx.read_barcodes(im,**kw)
  if not found:rows.append({'file':str(path),'format':'未検出','text':'','bytes_b64':'','valid':False,'position':[],'error':'コードが見つかりませんでした。'})
  for b in found[:100]:
   if len(b.bytes)>65536:raise ValueError('読み取り内容が64 KiBを超えました。')
   p=b.position;rows.append({'file':str(path),'format':str(b.format),'text':b.text,'bytes_b64':base64.b64encode(b.bytes).decode('ascii'),'valid':bool(b.valid),'position':[[v.x,v.y] for v in (p.top_left,p.top_right,p.bottom_right,p.bottom_left)],'error':str(b.error) if not b.valid else ''})
 return {'rows':rows,'png':preview}

def template(kind,values):
 if not isinstance(values,dict):raise ValueError('入力を確認してください。')
 def value(k):
  v=values.get(k,'');string(v,1000,True)
  if any(ord(c)<32 for c in v):raise ValueError('各欄は1行で入力してください。')
  return v
 def esc(v):return ''.join('\\'+c if c in '\\;,:"' else c for c in v)
 if kind=='wifi':
  ssid=value('ssid');pw=value('password');auth=value('auth');hidden=value('hidden')
  if not ssid or len(ssid.encode('utf8'))>32 or auth not in ('WPA','WEP','nopass') or hidden not in ('true','false'):raise ValueError('Wi-Fi名・方式・非表示設定を確認してください。')
  if auth!='nopass' and not pw:raise ValueError('Wi-Fiのパスワードを入力してください。')
  return f'WIFI:T:{auth};S:{esc(ssid)};P:{esc(pw) if auth!="nopass" else ""};H:{hidden};;'
 if kind=='contact':
  def vc(k):return value(k).replace('\\','\\\\').replace(';','\\;').replace(',','\\,')
  if not value('name'):raise ValueError('名前を入力してください。')
  return 'BEGIN:VCARD\r\nVERSION:3.0\r\nN:;'+vc('name')+';;;\r\nFN:'+vc('name')+'\r\nTEL:'+vc('phone')+'\r\nEMAIL:'+vc('email')+'\r\nORG:'+vc('org')+'\r\nEND:VCARD'
 if kind=='mail':
  from urllib.parse import quote,urlencode
  address=value('email')
  if not re.fullmatch(r'[^\s<>?&#]+@[^\s<>?&#]+',address):raise ValueError('メールアドレスを確認してください。')
  return 'mailto:'+quote(address,safe='@.+-')+'?'+urlencode({'subject':value('subject'),'body':value('body')})
 raise ValueError('入力形式を確認してください。')

def execute(task):
 if not isinstance(task,dict):raise ValueError('操作を確認してください。')
 mode=task['mode'];opts=task.get('opts',{})
 if mode=='qr':return make_qr(task['text'],opts)
 if mode=='barcode':return barcode(task['text'],task['format'],opts)
 if mode=='decode':return decode(task['paths'],opts)
 raise ValueError('使えない操作です。')
