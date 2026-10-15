"""Supported controls for the pinned whisper-cli build."""
import math
SCHEMA={
    'log-score':('b',None,None),
    'processors':('i',1,4),'offset-n':('i',0,100000),'max-context':('i',-1,16384),'max-len':('i',0,10000),
    'split-on-word':('b',None,None),'best-of':('i',1,16),'beam-size':('i',1,16),'audio-ctx':('i',0,1500),
    'word-thold':('f',0,1),'entropy-thold':('f',0,20),'logprob-thold':('f',-20,0),'no-speech-thold':('f',0,1),
    'temperature':('f',0,1),'temperature-inc':('f',0,1),'no-fallback':('b',None,None),'no-timestamps':('b',None,None),
    'carry-initial-prompt':('b',None,None),'dtw':('e',None,('tiny','tiny.en','base','base.en','small','small.en','medium','medium.en','large.v1','large.v2','large.v3','large.v3.turbo')),
    'suppress-nst':('b',None,None),'suppress-regex':('s',0,4096),'grammar':('s',0,8192),'grammar-rule':('s',0,128),'grammar-penalty':('f',0,1000),
    'no-flash-attn':('b',None,None),'flash-attn':('b',None,None),'detect-language':('b',None,None),'tinydiarize':('b',None,None),
    'vad-threshold':('f',0,1),'vad-min-speech-duration-ms':('i',0,60000),'vad-min-silence-duration-ms':('i',0,60000),
    'vad-max-speech-duration-s':('f',1,3600),'vad-speech-pad-ms':('i',0,30000),'vad-samples-overlap':('f',0,30),
}

def validate_advanced(opts):
    if not isinstance(opts, dict):
        raise ValueError("advanced must be a dict")
    out = {}
    for key in opts:
        if key not in SCHEMA:
            raise ValueError(f"unknown advanced key: {key}")
    for key, (kind, lo, hi) in SCHEMA.items():
        if key not in opts:
            continue
        v = opts[key]
        if kind == 'b':
            if not isinstance(v, bool):
                raise ValueError(f"{key} must be bool")
        elif kind == 'i':
            if isinstance(v, bool) or not isinstance(v, int):
                raise ValueError(f"{key} must be int")
            if v < lo or v > hi:
                raise ValueError(f"{key} out of range")
        elif kind == 'f':
            if isinstance(v, bool) or not isinstance(v, (int, float)):
                raise ValueError(f"{key} must be number")
            if v < lo or v > hi:
                raise ValueError(f"{key} out of range")
            fv = float(v)
            if math.isnan(fv) or math.isinf(fv):
                raise ValueError(f"{key} must be finite")
            if fv < lo or fv > hi:
                raise ValueError(f"{key} out of range")
        elif kind == 's':
            if not isinstance(v, str):
                raise ValueError(f"{key} must be string")
            if '\x00' in v:
                raise ValueError(f"{key} contains NUL")
            if len(v) < lo or len(v) > hi:
                raise ValueError(f"{key} length out of range")
        elif kind == 'e':
            if not isinstance(v, str):
                raise ValueError(f"{key} must be string")
            if v not in hi:
                raise ValueError(f"{key} invalid enum value")
        else:
            raise ValueError(f"unknown schema kind for {key}")
        out[key] = v
    if opts.get('flash-attn') is True and opts.get('no-flash-attn') is True:
        raise ValueError("flash-attn and no-flash-attn cannot both be true")
    return out

def build_args(model, source, prefix, language, translate, threads, vad_model, vad, diarize, offset_ms, duration_ms, prompt, advanced=None):
    if not isinstance(threads, int) or isinstance(threads, bool) or threads < 1 or threads > 32:
        raise ValueError("threads must be exact int 1..32")
    if not isinstance(offset_ms, int) or isinstance(offset_ms, bool) or offset_ms < 0 or offset_ms > 3600000:
        raise ValueError("offset_ms out of range")
    if not isinstance(duration_ms, int) or isinstance(duration_ms, bool) or duration_ms < 0 or duration_ms > 3600000:
        raise ValueError("duration_ms out of range")
    if not isinstance(prompt, str) or len(prompt) > 4096 or '\x00' in prompt:
        raise ValueError("prompt invalid")
    for name, val in (('translate', translate), ('vad', vad), ('diarize', diarize)):
        if not isinstance(val, bool):
            raise ValueError(f"{name} must be exact bool")
    opts = validate_advanced({} if advanced is None else advanced)
    procs = opts.get('processors', 1)
    if threads * procs > 32:
        raise ValueError("threads*processors exceeds 32")
    args = [
        '--no-gpu', '--model', str(model), '--file', str(source),
        '--output-file', str(prefix), '--language', language,
        '--threads', str(threads), '--output-json-full', '--output-txt',
        '--output-srt', '--output-vtt', '--output-lrc', '--output-csv',
        '--offset-t', str(offset_ms), '--duration', str(duration_ms)
    ]
    if translate:
        args.append('--translate')
    if diarize:
        args.append('--diarize')
    if vad:
        args.extend(['--vad', '--vad-model', str(vad_model)])
    if prompt:
        args.extend(['--prompt', prompt])
    for key, val in opts.items():
        if isinstance(val, bool):
            if val:
                args.append(f'--{key}')
        else:
            args.extend([f'--{key}', str(val)])
    return args
