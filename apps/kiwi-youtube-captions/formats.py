import re, json, csv, io, math

from urllib.parse import urlparse, parse_qs

from youtube_transcript_api._transcripts import FetchedTranscript, FetchedTranscriptSnippet

from youtube_transcript_api.formatters import TextFormatter, SRTFormatter, WebVTTFormatter

_ID_RE = re.compile(r'^[A-Za-z0-9_-]{11}$')

_HOSTS = {'youtube.com', 'www.youtube.com', 'm.youtube.com', 'music.youtube.com', 'youtu.be'}

def video_id(value: str) -> str:
    if not isinstance(value, str): raise ValueError('YouTubeの動画URLまたは11文字の動画IDを指定してください。')
    if len(value) > 2048 or '\x00' in value or any(ord(c) < 32 for c in value): raise ValueError('YouTubeの動画URLまたは11文字の動画IDを指定してください。')
    if _ID_RE.fullmatch(value): return value
    value=value.strip()
    p = urlparse(value)
    if p.scheme != 'https' or (p.port is not None and p.port != 443) or p.username or p.password:
        raise ValueError('YouTubeの動画URLまたは11文字の動画IDを指定してください。')
    host = (p.hostname or '').lower()
    path = p.path.removesuffix('/')
    if host in _HOSTS:
        if not (path.startswith('/') and not path.startswith('//')): raise ValueError('YouTubeの動画URLまたは11文字の動画IDを指定してください。')
        parts = path[1:].split('/')
        q = parse_qs(p.query, keep_blank_values=True)
        if len(q.get('v', []))>1:raise ValueError('YouTubeの動画URLまたは11文字の動画IDを指定してください。')
        if host == 'youtu.be':
            if len(parts) != 1 or not _ID_RE.fullmatch(parts[0]): raise ValueError('YouTubeの動画URLまたは11文字の動画IDを指定してください。')
            return parts[0]
        if parts == ['watch']:
            v_list = q.get('v', [])
            if len(v_list) != 1 or not _ID_RE.fullmatch(v_list[0]): raise ValueError('YouTubeの動画URLまたは11文字の動画IDを指定してください。')
            return v_list[0]
        if len(parts) == 2 and parts[0] in ('shorts', 'embed', 'live'):
            if not _ID_RE.fullmatch(parts[1]): raise ValueError('YouTubeの動画URLまたは11文字の動画IDを指定してください。')
            return parts[1]
    raise ValueError('YouTubeの動画URLまたは11文字の動画IDを指定してください。')

def clock(seconds: float) -> str:
    s = int(max(0, math.floor(seconds)))
    h, rem = divmod(s, 3600); m, sec = divmod(rem, 60)
    return f'{h:02d}:{m:02d}:{sec:02d}'

def matching(data: dict, query: str, lo=None, hi=None) -> list:
    if query is None or not isinstance(query, str): raise ValueError('query')
    q = query.casefold()
    if lo is not None and (not math.isfinite(lo) or lo < 0): raise ValueError('lo')
    if hi is not None and (not math.isfinite(hi) or hi < 0): raise ValueError('hi')
    if lo is not None and hi is not None and lo >= hi: raise ValueError('range')
    out = []
    for i, sn in enumerate(data.get('snippets', [])):
        t = str(sn.get('text', ''))
        st = float(sn.get('start', 0))
        if q in t.casefold() and (lo is None or st >= lo) and (hi is None or st < hi):
            out.append(i)
    return out

def _build_ft(data: dict) -> FetchedTranscript:
    snips = [FetchedTranscriptSnippet(text=s['text'], start=float(s.get('start', 0)), duration=float(s.get('duration', 0))) for s in data.get('snippets', [])]
    return FetchedTranscript(snippets=snips, video_id=data.get('video_id',''), language=data.get('language',''), language_code=data.get('language_code',''), is_generated=bool(data.get('is_generated', False)))

def render(data: dict, fmt: str, timestamps: bool = True) -> bytes:
    ft = _build_ft(data)
    f = fmt.lower()
    if f == 'txt':
        if not timestamps:
            return TextFormatter().format_transcript(ft).encode('utf-8')
        return '\n'.join(f'{clock(s["start"])} {s["text"]}' for s in data.get('snippets', [])).encode('utf-8')
    if f == 'json':
        obj = {'video_id': data.get('video_id',''), 'language': data.get('language',''), 'language_code': data.get('language_code',''), 'is_generated': bool(data.get('is_generated', False)), 'snippets': data.get('snippets', [])}
        if data.get('source') is not None: obj['source'] = data['source']
        return json.dumps(obj, ensure_ascii=False, indent=2).encode('utf-8')
    if f == 'srt':
        return SRTFormatter().format_transcript(ft).encode('utf-8')
    if f == 'vtt':
        return WebVTTFormatter().format_transcript(ft).encode('utf-8')
    if f == 'csv':
        buf = io.StringIO()
        w = csv.writer(buf, quoting=csv.QUOTE_MINIMAL)
        w.writerow(['start_seconds', 'duration_seconds', 'text'])
        for s in data.get('snippets', []):
            t = str(s.get('text', ''))
            t = _csv_guard(t)
            w.writerow([s.get('start', 0), s.get('duration', 0), t])
        return ('\ufeff' + buf.getvalue()).encode('utf-8')
    raise ValueError(f)

def _csv_guard(t: str) -> str:
    if t and (t.lstrip().startswith(('=', '+', '-', '@')) or t[0] in '\t\r\n'):
        return "'" + t
    return t

import re

_LANG_RE = re.compile(r"[A-Za-z][A-Za-z0-9-]{0,39}")
_PREFS = ("any", "manual", "generated")


def preferred_track(listing, options):
    langs = options.get("languages")
    pref = options.get("preference")
    if not isinstance(langs, list) or not (1 <= len(langs) <= 10):
        raise ValueError("languages must be a non-empty list of at most 10 items")
    for code in langs:
        if not isinstance(code, str) or _LANG_RE.fullmatch(code) is None:
            raise ValueError(f"invalid language code: {code!r}")
    if pref not in _PREFS:
        raise ValueError("preference must be 'any', 'manual', or 'generated'")
    if pref == "any":
        return listing.find_transcript(langs)
    if pref == "manual":
        return listing.find_manually_created_transcript(langs)
    return listing.find_generated_transcript(langs)
