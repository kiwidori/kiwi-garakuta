import base64, io, os
from PIL import Image
import qrcode
import zxingcpp
from qrcode.image.styles.moduledrawers.pil import (SquareModuleDrawer, GappedSquareModuleDrawer, CircleModuleDrawer,
    RoundedModuleDrawer, VerticalBarsDrawer, HorizontalBarsDrawer)
from qrcode.image.styles.colormasks import (SolidFillColorMask, RadialGradiantColorMask, SquareGradiantColorMask,
    HorizontalGradiantColorMask, VerticalGradiantColorMask)
from qrcode.image.styledpil import StyledPilImage
from qrcode.image.svg import SvgPathFillImage, SvgFillImage, SvgFragmentImage

_DRAWERS = {"square": SquareModuleDrawer, "gapped": GappedSquareModuleDrawer, "circle": CircleModuleDrawer,
            "rounded": RoundedModuleDrawer, "vertical": VerticalBarsDrawer, "horizontal": HorizontalBarsDrawer}
_GRADS = {"solid": SolidFillColorMask, "radial": RadialGradiantColorMask, "square": SquareGradiantColorMask,
          "horizontal": HorizontalGradiantColorMask, "vertical": VerticalGradiantColorMask}
_TYPES = {"version": int, "ecc": str, "box": int, "border": int, "optimize": int, "mask": int, "style": str,
          "foreground": str, "background": str, "color2": str, "gradient": str, "logo": str, "svg_kind": str}

def _hex(c):
    if not (isinstance(c, str) and len(c) == 7 and c[0] == "#"): raise ValueError("カラー形式が不正です")
    try: return tuple(int(c[i:i+2], 16) for i in (1, 3, 5))
    except ValueError: raise ValueError("カラー値が不正です")

def _lum(rgb):
    r, g, b = [v / 255.0 for v in rgb]
    f = lambda x: x / 12.92 if x <= 0.03928 else ((x + 0.055) / 1.055) ** 2.4
    return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b)

def _contrast(c1, c2):
    l1, l2 = sorted([_lum(c1), _lum(c2)], reverse=True)
    return (l1 + 0.05) / (l2 + 0.05)

def make_qr(text, opts):
    if not isinstance(text, str) or not text: raise ValueError("テキストが空です")
    if "\x00" in text: raise ValueError("NUL文字は使用できません")
    b = text.encode("utf-8")
    if len(b) > 3000: raise ValueError("テキストが長すぎます（最大3000バイト）")
    if not isinstance(opts, dict): raise ValueError("optsは辞書である必要があります")
    for k in opts:
        if k not in _TYPES: raise ValueError(f"不明なオプションキーです: {k}")
        if not isinstance(opts[k], _TYPES[k]) or (isinstance(opts[k], bool) and _TYPES[k] is int):
            raise ValueError(f"オプションの型が不正です: {k}")

    version = opts.get("version", 0)
    ecc = opts.get("ecc", "M")
    box = opts.get("box", 10)
    border = opts.get("border", 4)
    optimize = opts.get("optimize", 20)
    mask = opts.get("mask", -1)
    style = opts.get("style", "square")
    fg = _hex(opts.get("foreground", "#000000"))
    bg = _hex(opts.get("background", "#FFFFFF"))
    c2 = _hex(opts.get("color2", "#163b70"))
    grad = opts.get("gradient", "solid")
    logo_path = opts.get("logo", "")
    svg_kind = opts.get("svg_kind", "path")

    if version not in range(0, 41): raise ValueError("versionは0または1〜40である必要があります")
    if ecc not in ("L", "M", "Q", "H"): raise ValueError("eccが不正です")
    if not (2 <= box <= 16): raise ValueError("boxは2〜16である必要があります")
    if not (4 <= border <= 16): raise ValueError("borderは4〜16である必要があります")
    if not (0 <= optimize <= 100): raise ValueError("optimizeは0〜100である必要があります")
    if mask != -1 and not (0 <= mask <= 7): raise ValueError("maskは-1または0〜7である必要があります")
    if style not in _DRAWERS: raise ValueError("styleが不正です")
    if grad not in _GRADS: raise ValueError("gradientが不正です")
    if svg_kind not in ("path", "rect", "fragment"): raise ValueError("svg_kindが不正です")

    if _contrast(fg, bg) < 4.5: raise ValueError("前景と背景のコントラストが不足しています（4.5以上必要）")
    if grad != "solid" and (_contrast(c2, bg) < 4.5 or not (_lum(bg) > _lum(fg) and _lum(bg) > _lum(c2))):
        raise ValueError("グラデーション時のcolor2と背景のコントラストが不足しています")

    if _lum(bg) <= _lum(fg): raise ValueError("背景は線の色より明るくしてください")

    qr = qrcode.QRCode(version=version or None, error_correction=getattr(qrcode.constants, "ERROR_CORRECT_" + ecc), box_size=box, border=border, mask_pattern=None if mask == -1 else mask)
    qr.add_data(text, optimize=optimize)
    try:
        qr.make(fit=(version == 0))
    except qrcode.exceptions.DataOverflowError as e:
        raise ValueError("この設定では内容が入りません。内容を短くするか、版を0（自動）にしてください。") from e

    modules = qr.modules_count + border * 2
    side = modules * box
    if side > 2048: raise ValueError("出力サイズが2048pxを超えます")

    logo_img = None
    if logo_path:
        if ecc != "H": raise ValueError("ロゴ埋め込みにはECC Hが必要です")
        if not os.path.isabs(logo_path): raise ValueError("中央の画像は絶対パスで指定してください")
        ap = os.path.abspath(logo_path)
        if not os.path.isfile(ap): raise ValueError("ロゴファイルが見つかりません")
        if os.path.getsize(ap) > 2 * 1024 * 1024: raise ValueError("ロゴサイズが2MiBを超えます")
        try:
            with Image.open(ap) as im:
                if im.format not in ("PNG", "JPEG"): raise ValueError("ロゴはPNGまたはJPEGである必要があります")
                if im.width * im.height > 1_000_000: raise ValueError("ロゴピクセル数が100万を超えます")
                logo_img = im.copy()
        except Exception as e:
            raise ValueError(f"ロゴの読み込みに失敗しました: {e}")

    drawer = _DRAWERS[style]()
    if grad == "solid": color_mask = SolidFillColorMask(back_color=bg, front_color=fg)
    elif grad == "radial": color_mask = RadialGradiantColorMask(back_color=bg, center_color=fg, edge_color=c2)
    elif grad == "square": color_mask = SquareGradiantColorMask(back_color=bg, center_color=fg, edge_color=c2)
    elif grad == "horizontal": color_mask = HorizontalGradiantColorMask(back_color=bg, left_color=fg, right_color=c2)
    else: color_mask = VerticalGradiantColorMask(back_color=bg, top_color=fg, bottom_color=c2)

    pil_img = qr.make_image(image_factory=StyledPilImage, module_drawer=drawer, color_mask=color_mask,
                            embedded_image=logo_img, embedded_image_ratio=0.15 if logo_img else None).get_image()

    buf = io.BytesIO()
    pil_img.save(buf, format="PNG")
    png_bytes = buf.getvalue()
    if len(png_bytes) > 4 * 1024 * 1024: raise ValueError("PNG出力が4MiBを超えます")

    decoded = zxingcpp.read_barcodes(pil_img, formats=zxingcpp.BarcodeFormat.QRCode, text_mode=zxingcpp.TextMode.Plain)
    if not any(bar.valid and bar.bytes == b for bar in decoded): raise ValueError("QRコードの読み戻し検証に失敗しました")

    svg = ""
    if style == "square" and grad == "solid" and fg == (0, 0, 0) and bg == (255, 255, 255) and not logo_img:
        factory = {"path": SvgPathFillImage, "rect": SvgFillImage, "fragment": SvgFragmentImage}[svg_kind]
        svg = qr.make_image(image_factory=factory).to_string().decode("utf-8")

    return {
        "png": base64.b64encode(png_bytes).decode("ascii"),
        "svg": svg,
        "version": qr.version,
        "size": [pil_img.width, pil_img.height],
        "text": text
    }
