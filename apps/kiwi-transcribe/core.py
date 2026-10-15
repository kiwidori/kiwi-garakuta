"""Offline speech jobs with pinned assets and new-directory exports."""
import csv,ctypes,hashlib,io,json,os,re,secrets,shutil,struct,tempfile,threading,time,wave
from pathlib import Path
from runtime import execute,resource_path
from cli_args import build_args
from extra_exports import score_export
from duration_guard import safe_duration
ROOT=Path(__file__).resolve().parent
FORMATS={'txt','srt','vtt','lrc','csv','json'}
_ASSETS=None
_LOCK=threading.Lock()
def languages():return json.loads(Path(resource_path('languages.json',ROOT)).read_text(encoding='utf8'))
def assets():
    global _ASSETS
    with _LOCK:
        if _ASSETS is None:
            if os.name=='nt':
                win=ctypes.create_unicode_buffer(32768)
                if not ctypes.windll.kernel32.GetWindowsDirectoryW(win,len(win)):raise ValueError('Windowsの情報を取得できません。')
                if any(not (Path(win.value)/'System32'/name).is_file() for name in ('MSVCP140.dll','VCRUNTIME140_1.dll','VCOMP140.DLL')):raise ValueError('Microsoft Visual C++ v14 再頒布可能パッケージ（x64）をインストールしてください。')
            pin=json.loads(Path(resource_path('upstream-pin.json',ROOT)).read_text(encoding='utf8'))
            expected={**pin['members'],**{n:p['sha256'] for n,p in pin['models'].items()}}
            import zipfile
            cache=tempfile.TemporaryDirectory(prefix='kiwi-transcribe-native-')
            try:
                with zipfile.ZipFile(resource_path('native-payload.zip',ROOT)) as z:
                    if set(z.namelist())!=set(expected):raise ValueError('同梱ファイルの構成が違います。')
                    for name,digest in expected.items():
                        if '/' in name or '\\' in name:raise ValueError('同梱ファイル名が不正です。')
                        body=z.read(name)
                        if hashlib.sha256(body).hexdigest()!=digest:raise ValueError('同梱ファイルの検証に失敗しました。')
                        (Path(cache.name)/name).write_bytes(body)
            except BaseException:cache.cleanup();raise
            _ASSETS=cache
        return Path(_ASSETS.name)
def source_paths(paths):
    if not 1<=len(paths)<=20:raise ValueError('音声は1～20件選んでください。')
    result=[];total=0
    for path in paths:
        p=Path(path).resolve(strict=True)
        if not p.is_file() or p.suffix.lower() not in ('.wav','.mp3','.flac','.ogg'):raise ValueError('WAV・MP3・FLAC・OGGを選んでください。')
        size=p.stat().st_size
        if not 0<size<=200*1024*1024:raise ValueError('音声1件は200 MiBまでです。空のファイルは使えません。')
        total+=size;result.append(p)
    if total>1024**3:raise ValueError('音声は合計1 GiBまでです。')
    return result
def model_file(custom,folder):
    if not custom:return folder/'small.bin'
    p=Path(custom).resolve(strict=True)
    if not p.is_file() or not 1024<p.stat().st_size<=4*1024**3:raise ValueError('互換GGMLモデルを選んでください（最大4 GiB）。')
    with p.open('rb') as f:magic=f.read(4)
    if magic!=b'lmgg':raise ValueError('Whisper用GGMLモデルではありません。GGUFは使えません。')
    return p
def checked_document(path):
    if not path.is_file() or path.stat().st_size>16*1024**2:raise ValueError('認識結果がないか、16 MiBを超えました。')
    doc=json.loads(path.read_text(encoding='utf8'))
    rows=doc.get('transcription')
    if not isinstance(rows,list) or len(rows)>100000:raise ValueError('認識結果の形式を確認できません。')
    for row in rows:
        if not isinstance(row,dict) or not isinstance(row.get('text'),str):raise ValueError('認識した文章の形式が違います。')
        offsets=row.get('offsets',{});start=offsets.get('from');end=offsets.get('to')
        if type(start)!=int or type(end)!=int or not 0<=start<=end:raise ValueError('認識時刻の形式が違います。')
    doc.pop('systeminfo',None)
    if isinstance(doc.get('params'),dict):doc['params'].pop('model',None)
    return doc
def csv_body(doc):
    out=io.StringIO(newline='');w=csv.writer(out);speaker=any('speaker' in r for r in doc['transcription'])
    w.writerow(['start','end',*(['speaker'] if speaker else []),'text'])
    for row in doc['transcription']:
        text=row['text']
        if text.lstrip().startswith(('=','+','-','@')):text="'"+text
        w.writerow([row['offsets']['from'],row['offsets']['to'],*([row.get('speaker','')] if speaker else []),text])
    return out.getvalue().encode('utf-8-sig')
def probe_audio(source,model,folder,prefix,cancel,threads,cwd=None):
    args=['--no-gpu','--model',str(model),'--file',str(source),'--threads',str(threads),'--language','auto','--detect-language','--output-json-full','--output-file',str(prefix)]
    result=execute(str(folder/'whisper-cli.exe'),args,cwd=cwd or folder,cancel_event=cancel,timeout=90,max_output=1024**2)
    text=result['stderr'].decode('utf8',errors='replace')
    match=re.search(r'(?m)^main: processing [^\r\n]*\((\d+) samples,',text)
    if result['returncode']!=0 or not match:raise ValueError('音声を読み取れませんでした。対応形式とファイルを確認してください。')
    return int(match[1])
def run_batch(paths,destination,language='ja',mode='transcribe',threads=4,vad=False,diarize=False,offset_ms=0,duration_ms=0,prompt='',advanced=None,custom_model='',formats=None,cancel=None,notify=None):
    paths=source_paths(paths);dest=Path(destination).resolve(strict=True)
    if not dest.is_dir():raise ValueError('保存先の親フォルダーを選んでください。')
    if language not in {'auto',*languages()}:raise ValueError('一覧にある言語を選んでください。')
    if mode not in ('transcribe','translate','detect'):raise ValueError('操作を選んでください。')
    if type(duration_ms)!=int or not 0<=duration_ms<=3600000:raise ValueError('長さは0～3600秒です。')
    formats=set(formats or ('txt','srt','vtt'))
    if not formats<=FORMATS:raise ValueError('保存形式が違います。')
    if mode=='detect':formats={'json'}
    cancel=cancel or threading.Event();advanced=dict(advanced or {})
    if advanced.get('detect-language') and mode!='detect':raise ValueError('言語だけ調べる場合は、操作を「言語の判別のみ」にしてください。')
    advanced['detect-language']=mode=='detect'
    folder=assets();model=model_file(custom_model,folder)
    if advanced.get('tinydiarize') and not custom_model:raise ValueError('tinydiarizeには専用TDRZモデルを指定してください。')
    results=[]
    with tempfile.TemporaryDirectory(prefix='kiwi-transcribe-job-') as temp:
        job=Path(temp)
        if custom_model:shutil.copyfile(model,job/'model.bin')
        else:
            try:os.link(model,job/'model.bin')
            except OSError:shutil.copyfile(model,job/'model.bin')
        try:os.link(folder/'silero.bin',job/'vad.bin')
        except OSError:shutil.copyfile(folder/'silero.bin',job/'vad.bin')
        for index,source in enumerate(paths):
            if cancel.is_set():raise RuntimeError('文字起こしを停止しました。')
            if notify:notify(index,len(paths),source.name)
            prefix=job/('audio-'+str(index))
            local_source=job/('input-'+str(index)+source.suffix.lower());shutil.copyfile(source,local_source)
            args=build_args('model.bin',local_source.name,prefix.name,language,mode=='translate',threads,'vad.bin',vad,diarize,offset_ms,duration_ms,prompt,advanced)
            probe_prefix=job/('probe-'+str(index))
            samples=probe_audio(local_source.name,'model.bin',folder,probe_prefix.name,cancel,threads,cwd=job)
            duration=safe_duration(samples,offset_ms,duration_ms,vad,advanced.get('processors',1))
            args[args.index('--duration')+1]=str(duration)
            if mode=='detect':prefix=probe_prefix
            else:
                result=execute(str(folder/'whisper-cli.exe'),args,cwd=job,cancel_event=cancel,timeout=1800,max_output=16*1024**2)
                if result['returncode']!=0:raise RuntimeError('音声を認識できませんでした。対応形式とモデル、設定を確認してください。\n'+result['stderr'].decode('utf8',errors='replace')[-1500:].replace(str(folder),'[同梱モデル]'))
            doc=checked_document(prefix.with_suffix('.json'))
            if doc.get('model',{}).get('multilingual') is False and (mode=='translate' or language not in ('auto','en')):raise ValueError('選んだモデルは英語専用です。多言語モデルを使ってください。')
            lang=doc.get('result',{}).get('language','');text='\n'.join(row['text'].strip() for row in doc['transcription'])
            bodies={}
            for fmt in formats:
                if fmt=='json':body=(json.dumps(doc,ensure_ascii=False,indent=2,allow_nan=False)+'\n').encode('utf8')
                elif fmt=='csv':body=csv_body(doc)
                else:
                    f=prefix.with_suffix('.'+fmt)
                    if not f.is_file() or f.stat().st_size>16*1024**2:raise ValueError('保存データがないか、上限を超えました。')
                    body=f.read_bytes()
                if len(body)>16*1024**2:raise ValueError('保存データが16 MiBを超えました。')
                bodies[fmt]=body
            bodies.update(score_export(prefix,advanced.get('log-score',False) and mode!='detect'))
            if diarize and doc['transcription'] and not any('speaker' in r for r in doc['transcription']):raise ValueError('左右の区別にはステレオ音声を使ってください。')
            results.append({'mode':mode,'source':source.name,'text':text,'language':lang,'document':doc,'bodies':bodies})
            local_source.unlink()
        if cancel.is_set():raise RuntimeError('文字起こしを停止しました。')
        final=dest/('文字起こし-'+time.strftime('%Y%m%d-%H%M%S')+'-'+secrets.token_hex(3))
        with tempfile.TemporaryDirectory(prefix='.kiwi-transcribe-',dir=dest) as staging:
            for index,item in enumerate(results):
                title=re.sub(r'[<>:"/\\|?*\x00-\x1f]','_',Path(item['source']).stem)[:60].rstrip(' .') or 'audio'
                for fmt,body in item['bodies'].items():(Path(staging)/(f'{index+1:02d}-'+title+'.'+fmt)).write_bytes(body)
            if final.exists():raise ValueError('保存先が既に使われています。')
            Path(staging).rename(final)
    for item in results:item.pop('bodies')
    return {'folder':str(final),'items':results}
