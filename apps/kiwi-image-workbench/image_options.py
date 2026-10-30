"""options.py - Pure standardlib validation and ImageMagick CLI argument builder."""

import math


def _is_strict_int(value):
    """Check if value is a strict integer (rejects bool, float, strings)."""
    return isinstance(value, int) and not isinstance(value, bool)


def _is_bool(value):
    """Check if value is strictly a boolean."""
    return isinstance(value, bool)


def _is_finite_float(value):
    """Check if value is a finite number (rejects bool and strings)."""
    if isinstance(value, bool):
        return False
    if not isinstance(value, (int, float)):
        return False
    return math.isfinite(value)


def validate(raw: dict) -> dict:
    """Validate raw input dictionary and return a normalized validated dictionary.

    Raises ValueError for any invalid field or type.
    """
    if not isinstance(raw, dict):
        raise ValueError("Input must be a dict")

    v = {}

    # format
    fmt = raw.get("format", "JPEG")
    valid_formats = {"JPEG", "PNG", "WEBP", "BMP", "TIFF", "GIF", "ICO", "AVIF"}
    if not isinstance(fmt, str) or fmt not in valid_formats:
        raise ValueError(f"Invalid format: {fmt!r}")
    v["format"] = fmt

    # quality
    q = raw.get("quality", 85)
    if not _is_strict_int(q) or not (1 <= q <= 100):
        raise ValueError(f"Invalid quality: {q!r}")
    v["quality"] = q

    # size_mode
    sm = raw.get("size_mode", "none")
    valid_size_modes = {"none", "fit", "fill", "exact", "percent"}
    if not isinstance(sm, str) or sm not in valid_size_modes:
        raise ValueError(f"Invalid size_mode: {sm!r}")
    v["size_mode"] = sm

    # width / height
    w = raw.get("width", 1024)
    h = raw.get("height", 1024)
    if not _is_strict_int(w) or not (1 <= w <= 8000):
        raise ValueError(f"Invalid width: {w!r}")
    if not _is_strict_int(h) or not (1 <= h <= 8000):
        raise ValueError(f"Invalid height: {h!r}")
    v["width"] = w
    v["height"] = h

    # percent
    p = raw.get("percent", 100)
    if not _is_strict_int(p) or not (1 <= p <= 400):
        raise ValueError(f"Invalid percent: {p!r}")
    v["percent"] = p

    # upscale
    up = raw.get("upscale", False)
    if not _is_bool(up):
        raise ValueError(f"Invalid upscale: {up!r}")
    v["upscale"] = up

    # rotate
    rot = raw.get("rotate", 0)
    valid_rotates = {0, 90, 180, 270}
    if not _is_strict_int(rot) or rot not in valid_rotates:
        raise ValueError(f"Invalid rotate: {rot!r}")
    v["rotate"] = rot

    # flip / flop
    fl = raw.get("flip", False)
    fo = raw.get("flop", False)
    if not _is_bool(fl):
        raise ValueError(f"Invalid flip: {fl!r}")
    if not _is_bool(fo):
        raise ValueError(f"Invalid flop: {fo!r}")
    v["flip"] = fl
    v["flop"] = fo

    # crop_enabled
    ce = raw.get("crop_enabled", False)
    if not _is_bool(ce):
        raise ValueError(f"Invalid crop_enabled: {ce!r}")
    v["crop_enabled"] = ce

    # x0, y0
    x0 = raw.get("x", 0)
    y0 = raw.get("y", 0)
    if not _is_strict_int(x0) or not (0 <= x0 <= 8000):
        raise ValueError(f"Invalid x0: {x0!r}")
    if not _is_strict_int(y0) or not (0 <= y0 <= 8000):
        raise ValueError(f"Invalid y0: {y0!r}")
    v["x"] = x0
    v["y"] = y0

    # crop_width, crop_height
    cw = raw.get("crop_width", 100)
    ch = raw.get("crop_height", 100)
    if not _is_strict_int(cw) or not (1 <= cw <= 8000):
        raise ValueError(f"Invalid crop_width: {cw!r}")
    if not _is_strict_int(ch) or not (1 <= ch <= 8000):
        raise ValueError(f"Invalid crop_height: {ch!r}")
    v["crop_width"] = cw
    v["crop_height"] = ch

    # grayscale
    gr = raw.get("grayscale", False)
    if not _is_bool(gr):
        raise ValueError(f"Invalid grayscale: {gr!r}")
    v["grayscale"] = gr

    # brightness, contrast, saturation
    br = raw.get("brightness", 0)
    ct = raw.get("contrast", 0)
    st = raw.get("saturation", 100)
    if not _is_strict_int(br) or not (-100 <= br <= 100):
        raise ValueError(f"Invalid brightness: {br!r}")
    if not _is_strict_int(ct) or not (-100 <= ct <= 100):
        raise ValueError(f"Invalid contrast: {ct!r}")
    if not _is_strict_int(st) or not (0 <= st <= 200):
        raise ValueError(f"Invalid saturation: {st!r}")
    v["brightness"] = br
    v["contrast"] = ct
    v["saturation"] = st

    # gamma
    ga = raw.get("gamma", 1.0)
    if not _is_finite_float(ga) or not (0.1 <= ga <= 5.0):
        raise ValueError(f"Invalid gamma: {ga!r}")
    v["gamma"] = ga

    # sharpen, blur
    sh = raw.get("sharpen", 0.0)
    bl = raw.get("blur", 0.0)
    if not _is_finite_float(sh) or not (0.0 <= sh <= 5.0):
        raise ValueError(f"Invalid sharpen: {sh!r}")
    if not _is_finite_float(bl) or not (0.0 <= bl <= 5.0):
        raise ValueError(f"Invalid blur: {bl!r}")
    v["sharpen"] = sh
    v["blur"] = bl

    # normalize, negate
    no = raw.get("normalize", False)
    ne = raw.get("negate", False)
    if not _is_bool(no):
        raise ValueError(f"Invalid normalize: {no!r}")
    if not _is_bool(ne):
        raise ValueError(f"Invalid negate: {ne!r}")
    v["normalize"] = no
    v["negate"] = ne

    # sepia
    sp = raw.get("sepia", 0)
    if not _is_strict_int(sp) or not (0 <= sp <= 100):
        raise ValueError(f"Invalid sepia: {sp!r}")
    v["sepia"] = sp

    # strip, progressive, lossless
    stp = raw.get("strip", False)
    prg = raw.get("progressive", False)
    ls = raw.get("lossless", False)
    if not _is_bool(stp):
        raise ValueError(f"Invalid strip: {stp!r}")
    if not _is_bool(prg):
        raise ValueError(f"Invalid progressive: {prg!r}")
    if not _is_bool(ls):
        raise ValueError(f"Invalid lossless: {ls!r}")
    v["strip"] = stp
    v["progressive"] = prg
    v["lossless"] = ls

    # background
    bg = raw.get("background", "white")
    valid_backgrounds = {"white", "black", "transparent"}
    if not isinstance(bg, str) or bg not in valid_backgrounds:
        raise ValueError(f"Invalid background: {bg!r}")
    v["background"] = bg

    # Cross-field validation
    if v["size_mode"] == "fill" and not v["upscale"]:
        raise ValueError("size_mode 'fill' requires upscale=True")

    return v


def arguments(v: dict) -> list[str]:
    args = ["-auto-orient"]
    if v["crop_enabled"]:
        args += ["-crop", f"{v['crop_width']}x{v['crop_height']}+{v['x']}+{v['y']}", "+repage"]
    mode = v["size_mode"]
    if mode in {"fit", "fill", "exact"}:
        geometry = f"{v['width']}x{v['height']}"
        geometry += {"fit": "" if v["upscale"] else ">", "fill": "^", "exact": "!"}[mode]
        args += ["-resize", geometry]
        if mode == "fill":
            args += ["-gravity", "center", "-extent", f"{v['width']}x{v['height']}"]
    elif mode == "percent":
        args += ["-resize", f"{v['percent']}%"]
    if v["rotate"]:
        args += ["-rotate", str(v["rotate"])]
    for key in ("flip", "flop"):
        if v[key]:
            args.append("-" + key)
    if v["saturation"] != 100:
        args += ["-modulate", f"100,{v['saturation']},100"]
    if v["brightness"] or v["contrast"]:
        args += ["-brightness-contrast", f"{v['brightness']}x{v['contrast']}"]
    if v["gamma"] != 1:
        args += ["-gamma", str(v["gamma"])]
    for key in ("sharpen", "blur"):
        if v[key]:
            args += ["-" + key, f"0x{v[key]}"]
    if v["grayscale"]:
        args += ["-colorspace", "Gray"]
    if v["normalize"]:
        args.append("-auto-level")
    if v["negate"]:
        args.append("-negate")
    if v["sepia"]:
        args += ["-sepia-tone", f"{v['sepia']}%"]
    if v["background"] != "transparent" or v["format"] == "JPEG":
        background = "black" if v["background"] == "black" else "white"
        args += ["-background", background, "-alpha", "remove", "-alpha", "off"]
    if v["format"] in {"JPEG", "WEBP", "AVIF"}:
        args += ["-quality", str(v["quality"])]
    if v["format"] == "JPEG" and v["progressive"]:
        args += ["-interlace", "Plane"]
    if v["format"] == "WEBP" and v["lossless"]:
        args += ["-define", "webp:lossless=true"]
    if v["strip"]:
        args.append("-strip")
    return args
