"""Validated options for the GIF encoder."""
import math,re
COLORS=('','bt709','fcc','bt470bg','bt601','smpte240','ycgco')
def number(value,low,high,integer=False):
 if isinstance(value,bool):raise ValueError('数値を確認してください。')
 try:v=float(value)
 except (TypeError,ValueError):raise ValueError('数値を確認してください。')
 if not math.isfinite(v) or not low<=v<=high or (integer and not v.is_integer()):raise ValueError(f'数値は{low}～{high}で指定してください。')
 return int(v) if integer else v
def color(value):
 v=str(value).strip().removeprefix('#')
 if not re.fullmatch('[a-fA-F0-9]{6}',v):raise ValueError('色は6桁のHEX（例：FFFFFF）で指定してください。')
 return v.upper()
def validate(o,kind):
 if kind not in ('images','gif','y4m'):raise ValueError('入力方法を確認してください。')
 r=dict(fps=number(o.get('fps',5),.1,100),quality=number(o.get('quality',90),1,100,True),width=number(o.get('width',640),0,1600,True),height=number(o.get('height',0),0,1600,True),repeat=number(o.get('repeat',0),-1,32767,True),speed=number(o.get('speed',1),.01,1000),mode=o.get('mode','normal'),bounce=bool(o.get('bounce',False)),fit=o.get('fit','contain'),background=o.get('background','transparent'),space=o.get('space',''))
 if r['mode'] not in ('normal','fast','extra') or r['fit'] not in ('contain','crop') or r['background'] not in ('transparent','white','black') or r['space'] not in COLORS:raise ValueError('設定を確認してください。')
 for key in ('motion','lossy'):r[key]=None if str(o.get(key,'')).strip()=='' else number(o[key],1,100,True)
 r['matte']=color(o['matte']) if str(o.get('matte','')).strip() else ''
 values=str(o.get('fixed','')).replace('\n',',').split(',');r['fixed']=[color(v) for v in values if v.strip()]
 if len(r['fixed'])>16:raise ValueError('固定色は16色までです。')
 if kind!='images' and r['bounce']:raise ValueError('往復再生は「画像を並べる」で使えます。')
 if kind=='images' and r['speed']!=1:raise ValueError('画像の速さはFPSで調整してください。速度倍率は1にします。')
 if kind!='y4m' and r['space']:raise ValueError('色空間の指定はY4Mだけで使えます。')
 return r
def build(paths,output,o,kind):
 a=['--output',str(output),'--quiet',f'--repeat={o["repeat"]}','--quality',str(o['quality'])]
 if kind in ('images','y4m'):a+=['--fps',str(o['fps'])]
 if kind=='images':
  a+=['--no-sort']
  if o['bounce']:a+=['--bounce']
 else:a+=['--fast-forward',str(o['speed'])]
 for key,flag in [('width','width'),('height','height'),('motion','motion-quality'),('lossy','lossy-quality')]:
  if o[key]:a+=['--'+flag,str(o[key])]
 if o['mode']!='normal':a+=['--'+o['mode']]
 for v in o['fixed']:a+=['--fixed-color',v]
 if o['matte']:a+=['--matte',o['matte']]
 if o['space']:a+=['--y4m-color-override',o['space']]
 return [*a,'--',*[str(p) for p in paths]]
