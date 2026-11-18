# layout.py
"""きうい動画一覧シート - Contact sheet compositor (Pillow 13)."""
import io
import math
from PIL import Image, ImageDraw, ImageFont


def compose(frames: list[bytes], timestamps: list[float], title: str, columns: int, width: int, theme: str, show_title: bool, show_times: bool, font_path: str) -> bytes:
    # --- Validate inputs ---
    if not isinstance(frames, list) or not isinstance(timestamps, list):
        raise ValueError("frames and timestamps must be lists")
    n = len(frames)
    if n < 4 or n > 36:
        raise ValueError(f"Frame count {n} out of range 4..36")
    if len(timestamps) != n:
        raise ValueError("timestamps length mismatch")
    for i, t in enumerate(timestamps):
        if not isinstance(t, (int, float)) or math.isnan(t) or math.isinf(t) or t < 0:
            raise ValueError(f"Invalid timestamp at index {i}: {t!r}")
    if not isinstance(columns, int) or columns < 2 or columns > 6:
        raise ValueError(f"columns must be int 2..6, got {columns!r}")
    if not isinstance(width, int) or width < 160 or width > 480:
        raise ValueError(f"width must be int 160..480, got {width!r}")
    if theme not in ('明るい', '暗い'):
        raise ValueError(f"theme must be '明るい' or '暗い', got {theme!r}")
    if not isinstance(title, str):
        raise ValueError("title must be str")
    title = title[:64]

    # --- Decode frames safely ---
    th_w = width
    th_h = width * 9 // 16
    decoded = []
    for i, raw in enumerate(frames):
        if not isinstance(raw, (bytes, bytearray)):
            raise ValueError(f"Frame {i} is not bytes")
        try:
            with Image.open(io.BytesIO(bytes(raw))) as img:
                if img.format != 'PNG':
                    raise ValueError(f"Frame {i} is not PNG")
                if img.size != (th_w, th_h):
                    raise ValueError(f"Frame {i} size {img.size} != expected {(th_w, th_h)}")
                decoded.append(img.convert('RGB').copy())
        except Exception as e:
            raise ValueError(f"Failed to decode frame {i}: {e}") from e

    # --- Layout calculation ---
    pad = 12
    rows = math.ceil(n / columns)

    # Font loading
    try:
        font_title = ImageFont.truetype(font_path, 28) if show_title else None
        font_time = ImageFont.truetype(font_path, 14) if show_times else None
    except Exception as e:
        raise ValueError(f"Failed to load font from {font_path!r}: {e}") from e

    # Calculate header height
    header_h = 0
    if show_title and title:
        header_h = 50  # Fixed reasonable height for title bar

    # Calculate time label height
    time_h = 24 if show_times else 0

    # Total canvas size
    total_w = columns * th_w + (columns + 1) * pad
    total_h = header_h + rows * (th_h + time_h) + (rows + 1) * pad

    # Enforce limits: max 4096 per side, max 16M pixels
    if total_w > 4096 or total_h > 4096:
        raise ValueError(f"Canvas dimensions {total_w}x{total_h} exceed 4096 limit")
    if total_w * total_h > 16_000_000:
        raise ValueError(f"Canvas pixels {total_w * total_h} exceed 16M limit")

    # Theme colors
    if theme == '明るい':
        bg_color = (245, 245, 245)
        text_color = (30, 30, 30)
        header_bg = (220, 220, 220)
    else:
        bg_color = (30, 30, 30)
        text_color = (240, 240, 240)
        header_bg = (50, 50, 50)

    # --- Create canvas ---
    canvas = Image.new('RGB', (total_w, total_h), bg_color)
    draw = ImageDraw.Draw(canvas)

    # Draw header
    if show_title and title:
        draw.rectangle([0, 0, total_w, header_h], fill=header_bg)
        # Fit long names inside the header without changing the source filename.
        prefix = title
        while True:
            display_title = prefix + '…' if len(prefix) < len(title) else prefix
            bbox = draw.textbbox((0, 0), display_title, font=font_title)
            tw = bbox[2] - bbox[0]
            if tw <= total_w - 24 or not prefix:
                break
            prefix = prefix[:-1]
        tx = max(pad, (total_w - tw) // 2 - bbox[0])
        ty = (header_h - (bbox[3] - bbox[1])) // 2 - bbox[1]
        draw.text((tx, ty), display_title, fill=text_color, font=font_title)

    # Draw thumbnails and timestamps
    for i in range(n):
        col = i % columns
        row = i // columns

        x = pad + col * (th_w + pad)
        y = header_h + pad + row * (th_h + time_h + pad)

        # Paste thumbnail
        canvas.paste(decoded[i], (x, y))

        # Draw timestamp below
        if show_times:
            t = timestamps[i]
            # Round to nearest tenth first to avoid carry issues like 59.96 -> 60.0
            tenths_total = round(t * 10)
            h, rem_h = divmod(tenths_total, 36000)
            m, rem_m = divmod(rem_h, 600)
            s, tenths = divmod(rem_m, 10)
            time_str = f"{h:02d}:{m:02d}:{s:02d}.{tenths}"

            bbox = draw.textbbox((0, 0), time_str, font=font_time)
            tw = bbox[2] - bbox[0]
            tx = x + (th_w - tw) // 2
            ty = y + th_h + 4
            draw.text((tx, ty), time_str, fill=text_color, font=font_time)

    # --- Encode to PNG ---
    buf = io.BytesIO()
    canvas.save(buf, format='PNG', optimize=True)
    png_bytes = buf.getvalue()

    if len(png_bytes) > 32 * 1024 * 1024:
        raise ValueError("Output PNG exceeds 32MiB limit")

    return png_bytes
