"""Read a bounded local image and prepare stable crop coordinates."""
import base64,hashlib,io
from pathlib import Path
from PIL import Image,ImageOps,ImageDraw
Image.MAX_IMAGE_PIXELS=20_000_000

def load(path,rotation=0,region=None):
 p=Path(path)
 if not p.is_absolute() or not p.is_file():raise ValueError('通常のローカル画像ファイルを選んでください。')
 with p.open('rb') as f:raw=f.read(25*1024*1024+1)
 if len(raw)>25*1024*1024:raise ValueError('画像は25 MiBまでです。')
 if type(rotation)!=int or rotation not in (0,90,180,270):raise ValueError('回転は0・90・180・270度で指定してください。')
 with Image.open(io.BytesIO(raw)) as src:
  if src.format not in ('PNG','JPEG','WEBP','BMP','GIF','TIFF') or src.width*src.height>20_000_000:raise ValueError('対応形式・2,000万画素以内の画像を選んでください。')
  if min(src.size)<5 or max(src.size)/min(src.size)>100:raise ValueError('画像が細すぎるか小さすぎます。')
  src.seek(0);src.load();src=ImageOps.exif_transpose(src);original=list(src.size);im=Image.new('RGB',src.size,'white');rgba=src.convert('RGBA');im.paste(rgba,mask=rgba.getchannel('A'))
 im=im.rotate(-rotation,expand=True);im.thumbnail((2000,2000),Image.Resampling.LANCZOS);full=list(im.size)
 if region is not None:
  if not isinstance(region,list) or len(region)!=4 or any(type(n)!=int for n in region):raise ValueError('選択範囲を確認してください。')
  x0,y0,x1,y1=region
  if not 0<=x0<x1<=im.width or not 0<=y0<y1<=im.height or min(x1-x0,y1-y0)<5:raise ValueError('選択範囲は画像内の5px以上にしてください。')
  im=im.crop(tuple(region))
 return im,{'source_sha256':hashlib.sha256(raw).hexdigest(),'original_size':original,'full_size':full,'size':list(im.size),'rotation':rotation,'region':region}

def encode(im,limit=16*1024*1024):
 b=io.BytesIO();im.save(b,format='PNG')
 if b.tell()>limit:raise ValueError('PNGが出力上限を超えました。')
 return base64.b64encode(b.getvalue()).decode('ascii')

def preview(im):
 thumb=im.copy();thumb.thumbnail((850,650),Image.Resampling.LANCZOS);return encode(thumb,4*1024*1024)

def annotate(im,rows):
 draw=ImageDraw.Draw(im)
 for i,row in enumerate(rows):
  box=[tuple(p) for p in row['box']];draw.line([*box,box[0]],fill='#146b4d',width=2);draw.text(box[0],str(i+1),fill='#143b80',stroke_width=1,stroke_fill='white')
 return im
