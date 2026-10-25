"""Validated settings and a fixed set of video/audio conversion operations."""
import math,re
DEFAULTS={"mode":"video","codec":"h264","quality":23,"resolution":1280,"fps":0,"rotate":0,"flip":False,"flop":False,"start":0.0,"end":0.0,"crop":False,"x":0,"y":0,"width":640,"height":360,"mute":False,"audio_track":0,"volume":100,"normalize":False,"audio_format":"mp3","audio_kbps":192,"frame_format":"png","strip":True}

def validate(raw):
 v={**DEFAULTS,**raw}
 for k,choices in {"mode":{"video","audio","frame"},"codec":{"h264","hevc","vp9"},"resolution":{0,640,854,1280,1920},"fps":{0,24,25,30,50,60},"rotate":{0,90,180,270},"audio_format":{"mp3","m4a","wav","flac","opus"},"frame_format":{"png","jpg"}}.items():
  if type(v[k]) is not type(DEFAULTS[k]) or v[k] not in choices:raise ValueError("設定の選択肢を確認してください。")
 for k,lo,hi in [("quality",18,35),("x",0,4096),("y",0,4096),("width",2,4096),("height",2,4096),("audio_track",0,7),("volume",0,200),("audio_kbps",64,320)]:
  if type(v[k]) is not int or not lo<=v[k]<=hi:raise ValueError(f"{k}の指定範囲は{lo}～{hi}です。")
 for k in ["flip","flop","crop","mute","normalize","strip"]:
  if type(v[k]) is not bool:raise ValueError("チェック項目を確認してください。")
 for k in ["start","end"]:
  if type(v[k]) not in {int,float} or not math.isfinite(v[k]) or not 0<=v[k]<=7200:raise ValueError("開始・終了は0～7,200秒で指定してください。")
  v[k]=float(v[k])
 if v["end"] and v["end"]<=v["start"]:raise ValueError("終了は開始より後にしてください。")
 if v["crop"] and any(v[k]%2 for k in ["x","y","width","height"]):raise ValueError("切り抜きの座標と寸法は偶数で指定してください。")
 return v

def filters(v):
 result=[]
 if v["crop"]:result.append(f"crop={v['width']}:{v['height']}:{v['x']}:{v['y']}")
 if v["rotate"]==90:result.append("transpose=clock")
 elif v["rotate"]==270:result.append("transpose=cclock")
 elif v["rotate"]==180:result += ["hflip","vflip"]
 if v["flip"]:result.append("vflip")
 if v["flop"]:result.append("hflip")
 # Never enlarge small movies; square pixels follow the display aspect ratio.
 limit=v["resolution"]
 if limit:
  h={640:360,854:480,1280:720,1920:1080}[limit]
  result.append(f"scale=w='min(iw,{limit})':h='min(ih,{h})':force_original_aspect_ratio=decrease:force_divisible_by=2:reset_sar=1")
 else:result.append("scale=w=trunc(iw/2)*2:h=trunc(ih/2)*2:reset_sar=1")
 return result

def audio_filters(v):
 result=[]
 if v["normalize"]:result.append("loudnorm=I=-16:TP=-1.5:LRA=11")
 if v["volume"]!=100:result.append(f"volume={v['volume']/100:.3f}")
 return result

def output_extension(v):
 if v["mode"]=="frame":return v["frame_format"]
 if v["mode"]=="audio":return v["audio_format"]
 return "webm" if v["codec"]=="vp9" else "mp4"

def output_arguments(v,has_audio=True):
 if v["mode"]=="frame":return ["-map",f"0:{v.get('video_index',0)}","-vf",",".join(filters(v)),"-frames:v","1","-an",*(["-q:v","2"] if v["frame_format"]=="jpg" else [])]
 args=[]
 if v["end"]:args += ["-t",str(v["end"]-v["start"])]
 args += ["-map_metadata","-1" if v["strip"] else "0","-map_chapters","-1","-sn","-dn"]
 if v["mode"]=="video":
  args += ["-map",f"0:{v.get('video_index',0)}","-vf",",".join(filters(v)),"-pix_fmt","yuv420p","-threads","2"]
  if v["codec"]=="h264":args += ["-c:v","libx264","-preset","medium","-crf",str(v["quality"]),"-movflags","+faststart"]
  elif v["codec"]=="hevc":args += ["-c:v","libx265","-preset","fast","-crf",str(v["quality"]),"-x265-params","pools=2:frame-threads=2:wpp=0","-tag:v","hvc1","-movflags","+faststart"]
  else:args += ["-c:v","libvpx-vp9","-crf",str(v["quality"]),"-b:v","0","-deadline","good","-cpu-used","4","-row-mt","1"]
  if v["fps"]:args += ["-r",str(v["fps"])]
  if v["mute"] or not has_audio:return [*args,"-an"]
 else:args += ["-vn"]
 args += ["-map",f"0:a:{v['audio_track']}"]
 af=audio_filters(v)
 if af:args += ["-af",",".join(af)]
 fmt=v["audio_format"] if v["mode"]=="audio" else ("opus" if v["codec"]=="vp9" else "m4a")
 args += ["-c:a",{"mp3":"libmp3lame","m4a":"aac","wav":"pcm_s16le","flac":"flac","opus":"libopus"}[fmt],"-ar","48000","-ac","2"]
 if fmt not in {"wav","flac"}:args += ["-b:a",str(v["audio_kbps"])+"k"]
 return args
