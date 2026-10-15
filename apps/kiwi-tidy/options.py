import math

import json
from pathlib import Path
from runtime import resource_path
SCHEMA = json.loads(Path(resource_path('schema.json',Path(__file__).resolve().parent)).read_text(encoding='utf8'))
LIST_FLAGS = {"allowed-extensions", "excluded-extensions", "excluded-items", "extensions"}
ENUMS = {
    ("dup", "search-method"): {"NAME", "SIZE", "SIZE_NAME", "HASH"},
    ("music", "search-method"): {"TAGS", "CONTENT"},
    ("dup", "hash-type"): {"BLAKE3", "CRC32", "XXH3"},
    ("image", "hash-alg"): {"Mean", "Gradient", "Blockhash", "VertGradient", "DoubleGradient", "Median"},
    ("image", "image-filter"): {"Lanczos3", "Nearest", "Triangle", "Gaussian", "CatmullRom"},
    ("image", "geometric-invariance"): {"off", "mirror-flip", "mirror-flip-rotate90"},
}

def _bad(s):
    return len(s) > 2048 or any(ord(c) < 32 or ord(c) == 127 for c in s)

def validate_options(mode, options: dict) -> dict:
    if mode not in SCHEMA: raise ValueError("unknown mode")
    spec = SCHEMA[mode]
    if not isinstance(options, dict): raise ValueError("options must be dict")
    if len(options) > 63: raise ValueError("too many options")
    out = {}
    for k, v in options.items():
        if k not in spec: raise ValueError(f"unknown key {k}")
        t = spec[k]
        if t == "bool":
            if isinstance(v, bool): out[k] = v
            else: raise ValueError(f"bad bool {k}")
        elif t == "int":
            if isinstance(v, bool) or not isinstance(v, int): raise ValueError(f"bad int {k}")
            if k in ("minimal-file-size", "maximal-file-size") and not (0 <= v < 2**63): raise ValueError("size bound")
            elif k == "thread-number" and not (0 <= v <= 64): raise ValueError("threads")
            elif k == "max-difference" and not (0 <= v <= 40): raise ValueError("maxdiff")
            elif k == "hash-size" and v not in (8, 16, 32, 64): raise ValueError("hash-size")
            elif k == "number-of-files" and not (1 <= v <= 10000): raise ValueError("file count")
            out[k] = v
        elif t == "float":
            if isinstance(v, bool) or not isinstance(v, (int, float)): raise ValueError(f"bad float {k}")
            if isinstance(v, int) and abs(v) > 2**53: raise ValueError("huge integer")
            f = float(v)
            if not math.isfinite(f): raise ValueError("not finite")
            if k == "minimum-segment-duration" and not (0 <= f <= 3600): raise ValueError("duration")
            elif k == "maximum-difference" and not (0 < f <= 10): raise ValueError("music maxdiff")
            out[k] = f
        else:
            if not isinstance(v,str) or not v or len(v)>2048 or any(_bad(line) for line in v.split("\n")) or (k not in LIST_FLAGS and _bad(v)): raise ValueError(f"bad str {k}")
            if (mode,k) in ENUMS and v not in ENUMS[(mode,k)]: raise ValueError("enum")
            if k == "checked-types":
                toks = v.split()
                if any(t.startswith("VIDEO") for t in toks): raise ValueError("no VIDEO")
                allowed = {"PDF", "AUDIO", "IMAGE", "ARCHIVE", "FONT", "MARKUP"}
                if not toks or not set(toks) <= allowed: raise ValueError("checked-types")
            out[k] = v
    if "minimal-file-size" in out and "maximal-file-size" in out and out["minimal-file-size"] > out["maximal-file-size"]:
        raise ValueError("minimal > maximal")
    return out

def option_flags(mode,options):
    opts=validate_options(mode,options);flags=[]
    for k,v in opts.items():
        if type(v)==bool:
            if v:flags.append('--'+k)
        elif k in LIST_FLAGS or k=='extensions':
            for line in str(v).splitlines():
                if line and (line.startswith('-') or _bad(line)):raise ValueError('使えない設定値です。')
                if line:flags.append('--'+k+'='+line)
        elif k=='checked-types':
            flags.extend('--checked-types='+x for x in v.split())
        else:flags.append('--'+k+'='+str(v))
    if len(flags)>256 or sum(len(x) for x in flags)>16000:raise ValueError('設定が長すぎます。')
    return flags

def result_groups(mode: str, method: str, data) -> list[list[dict]]:
    groups: list[list[dict]] = []
    individualrowcount = 0
    groupmode = mode in ("dup", "image", "music")

    def is_entry(x):
        return isinstance(x,str) or (isinstance(x,dict) and "path" in x)

    def row(x, ref=False):
        nonlocal individualrowcount
        if not is_entry(x):
            raise ValueError("not an entry")
        p = x if isinstance(x,str) else x.get("path", "")
        if not isinstance(p, str) or len(p) > 32767:
            raise ValueError("bad path length")
        for ch in p:
            if ord(ch)<32 or ord(ch)==127:
                raise ValueError("NUL/control in path")
        out = {"path":x} if isinstance(x,str) else dict(x)
        out["reference"] = ref
        individualrowcount += 1
        if individualrowcount > 50000:
            raise ValueError("too many rows")
        return out

    def emit(entries):
        groups.append(list(entries))

    def walk(node):
        nonlocal individualrowcount
        if is_entry(node):
            emit([row(node)])
        elif isinstance(node, dict):
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            if not node:
                return
            first = node[0]
            second = node[1] if len(node) >= 2 else None
            if groupmode and len(node) == 2 and is_entry(first) and isinstance(second, list) \
                    and all(is_entry(c) for c in second):
                emit([row(first, True)] + [row(c) for c in second])
            elif all(is_entry(c) for c in node):
                if groupmode:
                    emit([row(c) for c in node])
                else:
                    for c in node:
                        emit([row(c)])
            else:
                for c in node:
                    walk(c)
        else:
            raise ValueError("unsupported node")

    walk(data)
    return groups
