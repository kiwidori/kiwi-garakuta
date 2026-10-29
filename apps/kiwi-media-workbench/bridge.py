"""Extract a bounded local video interval for the GIF editor."""
import math,tempfile
from pathlib import Path
from PIL import Image
import video_engine as engine
from video_options import filters

class Clip:
 def __init__(self):
  self.temp=tempfile.TemporaryDirectory(prefix='kiwi-media-frames-')
  self.directory=Path(self.temp.name);self.paths=[];self.fps=0;self.duration=0
 def close(self):self.temp.cleanup()

def extract(value,raw,fps,cancel):
 if isinstance(fps,bool):raise ValueError('GIFのFPSを確認してください。')
 try:fps=float(fps)
 except (TypeError,ValueError):raise ValueError('GIFのFPSを確認してください。')
 if not math.isfinite(fps) or not .1<=fps<=30:raise ValueError('動画からの取り込みは0.1～30 FPSです。')
 clip=Clip()
 try:
  work=clip.directory;source=engine.stage(value,work,cancel);info=engine.probe(source,work,cancel)
  # Audio-only selections must not bypass video and HDR validation.
  v=engine.plan(info,{**raw,'mode':'video','audio_track':0})
  duration=(v['end']-v['start']) if v['end'] else min(10.,info['duration']-v['start'])
  if duration>10.000001:raise ValueError('GIFへ渡す区間は10秒以内にしてください。終了が0なら最大10秒です。')
  count=math.ceil(duration*fps-1e-8)
  if not 2<=count<=100:raise ValueError('区間の長さ × GIFのFPSを2～100フレームにしてください。')
  frames=work/'frames';frames.mkdir()
  def budget():
   paths=list(frames.iterdir())
   if len(paths)>100 or sum(p.stat().st_size for p in paths)>256*1024**2:raise ValueError('取り込み画像が100枚・256 MiBを超えました。')
  # The bridge has its own canvas ceiling; legacy video export limits stay intact.
  vf=filters({**v,'resolution':1280})+[f'fps=fps={fps}:start_time=0:round=up']
  args=['-hide_banner','-nostdin','-v','error','-n',*engine.INPUT,'-filter_threads','2']
  if v['start']:args+=['-ss',str(v['start'])]
  args+=['-i',str(source),'-map',f"0:{v['video_index']}",'-t',str(duration),'-vf',','.join(vf),'-frames:v',str(count),'-an','-sn','-dn','-map_metadata','-1','-c:v','png','-threads','2',str(frames/'frame-%04d.png')]
  engine.call(args,work,cancel,timeout=120,budget=budget)
  paths=sorted(frames.glob('frame-*.png'));pixels=0
  if not 2<=len(paths)<=100:raise ValueError('2枚以上のフレームを取り込めませんでした。区間を長くしてください。')
  for path in paths:
   engine.check(cancel)
   with Image.open(path) as im:
    if im.format!='PNG' or im.width>1280 or im.height>720:raise ValueError('取り込み画像のサイズを確認できません。')
    pixels+=im.width*im.height;im.verify()
  if pixels>120000000:raise ValueError('取り込み画像の総画素数を超えました。')
  engine.check(cancel);source.unlink();clip.paths=[str(p) for p in paths];clip.fps=fps;clip.duration=len(paths)/fps
  return clip
 except BaseException:
  clip.close();raise
