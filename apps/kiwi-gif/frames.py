import threading
import warnings
from pathlib import Path
from PIL import Image, ImageOps


def normalize_frames(
    paths: list[str],
    directory: str | Path,
    cancel: threading.Event,
    fit: str = "contain",
    background: str = "transparent",
    progress=None,
) -> tuple[list[str], tuple[int, int]]:
    if not (2 <= len(paths) <= 100):
        raise ValueError("画像は2～100枚を選んでください。")
    if fit not in ("contain", "crop"):
        raise ValueError("画像のサイズ合わせを確認してください。")
    if background not in ("transparent", "white", "black"):
        raise ValueError("背景の設定を確認してください。")

    dir_p = Path(directory)
    if not dir_p.is_dir():
        raise NotADirectoryError("一時フォルダーを確認してください。")
    if any(dir_p.iterdir()):
        raise FileExistsError("一時フォルダーが空ではありません。上書きはしません。")

    allowed_formats = {"PNG", "JPEG", "WEBP", "BMP", "GIF", "TIFF"}
    total_in = 0
    total_px = 0
    staged_bytes = 0
    canvas_wh: tuple[int, int] | None = None
    out_paths: list[str] = []

    for i, p in enumerate(paths):
        if cancel.is_set():
            raise InterruptedError("処理が中断されました")

        pp = Path(p)
        sz = pp.stat().st_size
        total_in += sz
        if sz > 25 * 1024**2:
            raise ValueError(f"画像は各25 MiBまでです：{pp.name}")
        if total_in > 256 * 1024**2:
            raise ValueError("入力は合計256 MiBまでです。")

        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            try:
                with Image.open(pp) as im:
                    if im.format not in allowed_formats:
                        raise ValueError(f"PNG・JPEG・WebP・BMP・GIF・TIFFを選んでください：{pp.name}")
                    im.seek(0)
                    w, h = im.size
                    total_px += w * h
                    if w * h > 12_000_000:
                        raise ValueError(f"画像は各1,200万画素までです：{pp.name}")
                    if total_px > 120_000_000:
                        raise ValueError("画像は合計1億2,000万画素までです。")

                    oriented = ImageOps.exif_transpose(im)
                    try:
                        frame = oriented.convert("RGBA")
                        frame.load()
                    finally:
                        oriented.close()
            except (Image.DecompressionBombError, Image.DecompressionBombWarning, OSError) as e:
                raise ValueError(f"画像の読み込みに失敗しました（破損または不正な形式）: {p}") from e

        if cancel.is_set():
            raise InterruptedError("処理が中断されました")

        if canvas_wh is None:
            sample = frame.copy()
            sample.thumbnail((1280, 1280), Image.Resampling.LANCZOS)
            canvas_wh = sample.size
            sample.close()

        cw, ch = canvas_wh

        if fit == "crop":
            frame = ImageOps.fit(frame, (cw, ch), method=Image.Resampling.LANCZOS)
        elif fit == "contain":
            tmp = frame.copy()
            tmp.thumbnail((cw, ch), Image.Resampling.LANCZOS)
            canvas = Image.new("RGBA", (cw, ch), (0, 0, 0, 0))
            x = (cw - tmp.width) // 2
            y = (ch - tmp.height) // 2
            canvas.alpha_composite(tmp, dest=(x, y))
            frame = canvas
        else:
            raise ValueError(f"invalid fit mode: {fit}")

        if background != "transparent":
            bg_color = (255, 255, 255, 255) if background == "white" else (0, 0, 0, 255)
            bg = Image.new("RGBA", (cw, ch), bg_color)
            frame = Image.alpha_composite(bg, frame)

        out_p = dir_p / f"{i:04d}.png"
        if out_p.exists():
            raise FileExistsError(f"output already exists: {out_p}")

        with open(out_p, "xb") as f:
            frame.save(f, format="PNG")

        staged_bytes += out_p.stat().st_size
        if staged_bytes > 512 * 1024**2:
            raise ValueError("一時ファイルが512 MiBを超えました。画像を減らしてください。")

        out_paths.append(str(out_p))
        if progress is not None:
            progress(i + 1, len(paths))
        if cancel.is_set():
            raise InterruptedError("処理が中断されました")

    return (out_paths, canvas_wh)
