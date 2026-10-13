"""Fetch public caption tracks using youtube-transcript-api."""
import time,math,json
from urllib.parse import urlsplit
import requests
from youtube_transcript_api import YouTubeTranscriptApi
from formats import video_id,preferred_track

class TimedSession(requests.Session):
    def __init__(self,cancel,proxy=''):
        super().__init__();self.cancel=cancel;self.deadline=time.monotonic()+90
        if proxy:
            parsed=urlsplit(proxy)
            if parsed.scheme not in ('http','https') or not parsed.hostname:raise ValueError('HTTPまたはHTTPSのプロキシURLを指定してください。')
            self.trust_env=False;self.proxies={'http':proxy,'https':proxy}
    def check(self):
        if self.cancel.is_set():raise InterruptedError('取得を停止しました。')
        if time.monotonic()>self.deadline:raise TimeoutError('取得に時間がかかるため停止しました。')
    def request(self,*args,**kwargs):
        self.check();remaining=max(.1,self.deadline-time.monotonic());kwargs['timeout']=(min(5,remaining),min(15,remaining));kwargs['stream']=True
        response=super().request(*args,**kwargs)
        try:
            body=bytearray()
            for chunk in response.iter_content(65536):
                self.check();body.extend(chunk)
                if len(body)>8*1024*1024:raise ValueError('応答が大きすぎます。')
            response._content=bytes(body);response._content_consumed=True
        finally:response.close()
        return response

ERRORS={'TranscriptsDisabled':'この動画では字幕が公開されていません。','NoTranscriptFound':'指定した言語の字幕が見つかりません。','VideoUnavailable':'動画を取得できません。公開状態を確認してください。','VideoUnplayable':'この動画は現在取得できません。','RequestBlocked':'YouTubeがこの接続からの取得を制限しています。時間を置いて試してください。','IpBlocked':'YouTubeがこの接続からの取得を制限しています。','AgeRestricted':'年齢確認が必要な動画には対応していません。','NotTranslatable':'この字幕は翻訳できません。','TranslationLanguageNotAvailable':'選んだ翻訳先を利用できません。'}
def execute_job(mode,options,cancel):
    ident=video_id(options['url'])
    try:
        with TimedSession(cancel,options.get('proxy','')) as session:
            listing=YouTubeTranscriptApi(http_client=session).list(ident);tracks=list(listing);session.check()
            if mode=='list':
                return {'video_id':ident,'tracks':[{'code':t.language_code,'language':t.language,'generated':t.is_generated,'translatable':t.is_translatable,'translations':[{'language':l.language,'language_code':l.language_code} for l in t.translation_languages]} for t in tracks]}
            if mode=='fetchauto':track=preferred_track(listing,options)
            elif mode=='fetch':track=next((t for t in tracks if t.language_code==options['code'] and t.is_generated==options['generated']),None)
            else:raise ValueError('操作が不正です。')
            if track is None:raise ValueError('字幕一覧が変わりました。もう一度一覧を取得してください。')
            source={'language':track.language,'code':track.language_code,'generated':track.is_generated}
            if options.get('translate'):track=track.translate(options['translate'])
            fetched=track.fetch(preserve_formatting=bool(options.get('preserve')));session.check();snippets=fetched.to_raw_data()
            if len(snippets)>20000:raise ValueError('字幕は20,000行までです。')
            for s in snippets:
                if not isinstance(s['text'],str):raise ValueError('字幕の形式が不正です。')
                for field in ('start','duration'):
                    n=s[field]
                    if isinstance(n,bool) or not isinstance(n,(int,float)) or not math.isfinite(n) or not 0<=n<=1e9:raise ValueError('字幕の時刻が不正です。')
            data={'video_id':ident,'language':fetched.language,'language_code':fetched.language_code,'is_generated':fetched.is_generated,'source':source,'snippets':snippets}
            if len(json.dumps(data,ensure_ascii=False).encode('utf8'))>5*1024*1024:raise ValueError('字幕は5 MiBまでです。')
            return data
    except requests.RequestException as error:
        if cancel.is_set():raise InterruptedError('取得を停止しました。') from None
        raise ValueError('接続できませんでした。ネットワーク設定を確認してください。（'+type(error).__name__+'）') from None
    except (InterruptedError,TimeoutError,ValueError):raise
    except Exception as error:
        name=type(error).__name__;raise ValueError(ERRORS.get(name,'字幕を取得できませんでした。接続や動画の状態を確認してください。')+'（'+name+'）') from None
