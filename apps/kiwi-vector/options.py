"""Typed VTracer configuration and CLI arguments."""
import math
import re

PRESETS = {
    "白黒": {"colormode": "bw", "hierarchical": "stacked", "mode": "spline", "filter_speckle": 4, "color_precision": 6, "gradient_step": 16, "corner_threshold": 60, "segment_length": 4.0, "splice_threshold": 45, "path_precision": 2},
    "イラスト": {"colormode": "color", "hierarchical": "stacked", "mode": "spline", "filter_speckle": 4, "color_precision": 8, "gradient_step": 16, "corner_threshold": 60, "segment_length": 4.0, "splice_threshold": 45, "path_precision": 2},
    "写真": {"colormode": "color", "hierarchical": "stacked", "mode": "spline", "filter_speckle": 10, "color_precision": 8, "gradient_step": 48, "corner_threshold": 180, "segment_length": 4.0, "splice_threshold": 45, "path_precision": 2},
}

RANGES = {
    "filter_speckle": (0, 16),
    "color_precision": (1, 8),
    "gradient_step": (0, 255),
    "corner_threshold": (0, 180),
    "segment_length": (3.5, 10),
    "splice_threshold": (0, 180),
    "path_precision": (0, 8),
}

ENUMS = {
    "colormode": ("color", "bw"),
    "hierarchical": ("stacked", "cutout"),
    "mode": ("pixel", "polygon", "spline"),
}

INT_KEYS = {"filter_speckle", "color_precision", "gradient_step", "corner_threshold", "splice_threshold", "path_precision"}


def _to_float(v):
    if isinstance(v, bool) or not isinstance(v, (int, float, str)):
        raise ValueError("数値形式が不正です")
    try:
        f = float(v)
    except (ValueError, TypeError):
        raise ValueError("数値形式が不正です")
    if not math.isfinite(f):
        raise ValueError("有限な数値を指定してください")
    return f


def _to_int(key, v):
    f = _to_float(v)
    if key in INT_KEYS:
        if isinstance(v, str) and not re.fullmatch(r"[+-]?\d+", v):
            raise ValueError("整数を指定してください")
        if not float(f).is_integer():
            raise ValueError("整数を指定してください")
    return int(f)


def validate(values):
    out = {"background": "white"}
    for k, v in values.items():
        if k == "background":
            if v not in ("original", "white"):
                raise ValueError("背景は original または white を指定してください")
            out[k] = v
        elif k in ENUMS:
            if v not in ENUMS[k]:
                raise ValueError(f"{k} は {', '.join(ENUMS[k])} のいずれかを指定してください")
            out[k] = v
        elif k in RANGES:
            f = _to_float(v)
            lo, hi = RANGES[k]
            if not (lo <= f <= hi):
                raise ValueError(f"{k} は {lo}〜{hi} の範囲を指定してください")
            out[k] = _to_int(k, v) if k in INT_KEYS else f
        else:
            raise ValueError("不明なキーです")
    for k in RANGES:
        if k not in out:
            raise ValueError(f"{k} が不足しています")
    for k in ENUMS:
        if k not in out:
            raise ValueError(f"{k} が不足しています")
    return out


def build(input_path, output_path, values):
    v = validate(values)
    argv = ["--input", str(input_path), "--output", str(output_path)]
    flags = [
        ("colormode", "color"),
        ("hierarchical", "stacked"),
        ("mode", "spline"),
        ("filter_speckle", 4),
        ("color_precision", 8),
        ("gradient_step", 16),
        ("corner_threshold", 60),
        ("segment_length", 4.0),
        ("splice_threshold", 45),
        ("path_precision", 2),
    ]
    for key, _ in flags:
        val = v[key]
        argv.append(f"--{key}")
        argv.append(str(val))
    return argv
