import os,shutil,tempfile,threading,sys,hashlib,json,zipfile
from pathlib import Path
from PIL import Image
from runtime import execute,resource_path

MODELS = {
    "写真": "realesrgan-x4plus",
    "イラスト": "realesrgan-x4plus-anime",
    "軽量イラスト": "realesr-animevideov3"
}
VALID_EXTS = {".jpg", ".jpeg", ".png", ".webp"}
MAX_FILES, MAX_SRC_MP, MAX_OUT_MP, TIMEOUT, MAX_OUT_BYTES = 50, 4_000_000, 64_000_000, 180, 1_048_576

_NATIVE_MANAGER=None
def _native_folder():
    global _NATIVE_MANAGER
    if not getattr(sys,'frozen',False):return Path(__file__).parent/'native'
    if _NATIVE_MANAGER is not None:return Path(_NATIVE_MANAGER.name)
    pin=json.loads(Path(resource_path('upstream-pin.json')).read_text(encoding='utf8'))
    manager=tempfile.TemporaryDirectory(prefix='kiwi-image-native-')
    try:
        with zipfile.ZipFile(resource_path('native-payload.zip')) as z:
            if set(z.namelist())!=set(pin['members']):raise ValueError('同梱エンジンの内容が一致しません。')
            for name,digest in pin['members'].items():
                if name!='realesrgan-ncnn-vulkan.exe' and not (name.startswith('models/') and Path(name).suffix in ('.bin','.param')):raise ValueError('無効な同梱ファイル名です。')
                dest=Path(manager.name)/name
                if not dest.resolve().is_relative_to(Path(manager.name).resolve()):raise ValueError('無効な同梱パスです。')
                body=z.read(name)
                if hashlib.sha256(body).hexdigest()!=digest:raise ValueError('同梱エンジンが一致しません。')
                dest.parent.mkdir(exist_ok=True);dest.write_bytes(body)
    except Exception:
        manager.cleanup();raise
    _NATIVE_MANAGER=manager
    return Path(manager.name)

def _validate(settings):
    if settings.get("model") not in MODELS: raise ValueError("モデルが不正です。")
    if type(settings.get("scale")) is not int or settings.get("scale") not in (2, 3, 4): raise ValueError("倍率が不正です。")
    if settings.get("format", "png").lower() not in ("png", "jpg", "webp"): raise ValueError("出力形式が不正です。")
    t = settings.get("tile", 0)
    if not isinstance(t, int) or (t != 0 and not 32 <= t <= 2048): raise ValueError("タイルサイズが不正です。")
    g = settings.get("gpu", "auto")
    if g != "auto" and (not isinstance(g, int) or g < 0 or g > 7): raise ValueError("GPU指定が不正です。")
    th = str(settings.get("threads", "1:1:1")).split(":")
    if len(th) != 3 or any(not x.isdigit() or not (1 <= int(x) <= 4) for x in th): raise ValueError("スレッド数が不正です。")
    if settings.get("tta", False) is not True and settings.get("tta", False) is not False: raise ValueError("TTAが不正です。")
    if MODELS[settings["model"]] != "realesr-animevideov3" and settings["scale"] != 4: raise ValueError("写真・イラストは4倍を選んでください。")

def _prepare(src, tmp_dir, fmt='png'):
    from PIL import ImageOps
    with Image.open(Path(src)) as original:
        if getattr(original, "is_animated", False): raise ValueError("アニメーション画像は対応していません。")
        actual_fmt = (original.format or "").upper()
        if actual_fmt not in ("PNG", "JPEG", "WEBP"): raise ValueError(f"非対応形式です: {actual_fmt}")
        w, h = original.size
        if w * h > 4_000_000: raise ValueError(f"ソースが4MPを超えます ({w}x{h})。")
        if original.mode in ("I", "I;16", "I;16B", "I;16L", "F"): raise ValueError("HDR/16bitモードは対応していません。")

        img = ImageOps.exif_transpose(original)
        w, h = img.size

        has_alpha = "A" in img.getbands() or "transparency" in img.info
        if fmt == 'jpg' and has_alpha:
            bg = Image.new("RGB", img.size, (255, 255, 255))
            alpha_img = img.convert("RGBA")
            bg.paste(alpha_img, mask=alpha_img.split()[-1])
            img = bg
        elif has_alpha:
            img = img.convert("RGBA")
        else:
            img = img.convert("RGB")

        clean_img = Image.frombytes(img.mode, img.size, img.tobytes())

    tmp_png = Path(tmp_dir) / "input.png"
    try:
        clean_img.save(tmp_png, "PNG")
    except Exception as e:
        raise ValueError(f"画像の読み込みに失敗しました: {e}")

    return tmp_png, w, h

def _publish(tmp_out, dest_dir, stem, scale, fmt):
    if os.name != 'nt': return None, "Windows環境でのみ実行可能です。"
    ext = f".{fmt}" if fmt != "jpg" else ".jpg"
    name = f"{stem}-enlarged-scale{scale}{ext}"
    final_path = Path(dest_dir) / name

    for existing in Path(dest_dir).iterdir():
        if existing.name.casefold() == name.casefold(): return None, "同名ファイルが存在するためスキップしました。"

    try:
        with tempfile.TemporaryDirectory(prefix='kiwi-save-', dir=dest_dir) as stage_dir:
            stage_path = Path(stage_dir) / f"result{ext}"
            shutil.copyfile(tmp_out, stage_path)
            os.rename(stage_path, final_path)
        return final_path, None
    except FileExistsError:
        return None, "同名ファイルが存在するためスキップしました。"
    except OSError as e:
        return None, f"保存に失敗しました: {e}"

def run_batch(paths, destination, settings, cancel, notify):
    _validate(settings)
    if cancel.is_set():raise InterruptedError("処理を停止しました。")
    import ctypes
    if os.name != 'nt':raise ValueError("Windows 11 x64で実行してください。")
    for dll,label in [('vulkan-1.dll','Vulkan対応GPUドライバー'),('vcomp140.dll','Microsoft Visual C++ v14 (x64)')]:
        try:ctypes.WinDLL(dll,winmode=0x800)
        except OSError as e:raise ValueError(label+'が見つかりません。インストールまたは更新してからお試しください。') from e
    if not isinstance(destination, (str, Path)) or not str(destination).strip():
        raise ValueError("出力先ディレクトリが指定されていません。")
    dest_dir = Path(destination).resolve()
    if "\x00" in str(dest_dir):
        raise ValueError("無効なパスです。")
    try:
        dest_dir.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        raise ValueError(f"出力先ディレクトリを作成できません: {e}")

    selected = []
    seen = set()
    for p in paths:
        pp = Path(p).resolve()
        if not pp.is_file():
            raise ValueError(f"画像が見つかりません: {pp.name}")
        if pp.suffix.lower() not in VALID_EXTS:
            raise ValueError(f"非対応のファイル形式です: {pp.name}")
        key = str(pp).casefold()
        if key in seen:
            continue
        seen.add(key)
        selected.append(pp)

    if not 1 <= len(selected) <= MAX_FILES:
        raise ValueError("選択されたファイル数が1〜50件の範囲外です。")

    native_dir = _native_folder()
    exe = native_dir / "realesrgan-ncnn-vulkan.exe"
    models_dir = native_dir / "models"
    fmt_map = {'png': 'PNG', 'jpg': 'JPEG', 'webp': 'WEBP'}
    results = []

    for src in selected:
        if cancel.is_set():
            raise InterruptedError("処理を停止しました。")

        record = {"source": str(src), "output": "", "status": "failed", "error": "", "size": ""}
        tmp_dir = tempfile.mkdtemp(prefix="kiwi-")
        try:
            scale = settings["scale"]
            fmt = settings["format"].lower()

            out_name = f"{src.stem}-enlarged-scale{scale}.{fmt}"
            final_path = dest_dir / out_name

            if str(final_path.resolve()).casefold() in seen or any(p.name.casefold() == out_name.casefold() for p in dest_dir.iterdir()):
                record["status"] = "skipped"
                record["error"] = "同名ファイルが存在するためスキップしました。"
                results.append(record)
                notify(record)
                continue

            tmp_in, w, h = _prepare(src, tmp_dir, fmt)
            exp_w, exp_h = w * scale, h * scale
            if exp_w * exp_h > MAX_OUT_MP:
                raise ValueError(f"出力が64MPを超えます ({exp_w}x{exp_h})。")

            args = [
                "-i", str(tmp_in),
                "-o", str(Path(tmp_dir) / f"out.{fmt}"),
                "-f", fmt,
                "-s", str(scale),
                "-m", str(models_dir),
                "-n", MODELS[settings["model"]],
                "-t", str(settings.get("tile", 0)),
                "-j", str(settings.get("threads", "1:1:1"))
            ]
            if settings.get("gpu") != "auto": args.extend(["-g", str(settings["gpu"])])
            if settings.get("tta"): args.append("-x")
            if settings.get("verbose"): args.append("-v")

            res = _execute_gpu(exe, args, native_dir, cancel)
            stderr_text = res["stderr"].decode(errors="replace")[:4096]
            record['log']=stderr_text

            if res["returncode"] != 0:
                if 'vkAllocateMemory failed' in stderr_text:raise RuntimeError('GPUメモリが不足しました。タイルを32に下げ、TTAを外すか、軽量イラストを選んでください。')
                raise RuntimeError(f"ネイティブ実行失敗 (Vulkan GPUまたはMicrosoft VC++ x64ランタイムを確認): {stderr_text}")

            tmp_out = Path(tmp_dir) / f"out.{fmt}"
            with Image.open(tmp_out) as im:
                im.load()
                if im.format != fmt_map[fmt]: raise ValueError("出力形式が一致しません。")
                if im.size != (exp_w, exp_h): raise ValueError("出力サイズが期待値と一致しません。")

            if cancel.is_set():raise InterruptedError("処理を停止しました。")
            final_path, err = _publish(tmp_out, dest_dir, src.stem, scale, fmt)
            if err:
                record["status"] = "skipped" if "スキップ" in err else "failed"
                record["error"] = err
            else:
                record["output"] = str(final_path)
                record["size"] = f"{w} × {h} → {exp_w} × {exp_h}"
                record["status"] = "completed"

        except InterruptedError:
            raise
        except Exception as e:
            record["error"] = str(e)
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

        results.append(record)
        notify(record)
    return results

def gather_folder(folder):
    files = []
    for p in sorted(Path(folder).iterdir()):
        if p.is_file() and p.suffix.lower() in VALID_EXTS: files.append(p)
    if len(files) > MAX_FILES: raise ValueError("50ファイルを超えるフォルダは処理できません。")
    return files

def _execute_gpu(exe, args, cwd, cancel):
    import re, time
    TIMEOUT = 180
    MAX_OUT_BYTES = 1 << 20
    start_time = time.monotonic()
    result = execute(exe, args, stdin_data=None, cwd=str(cwd), cancel_event=cancel, timeout=TIMEOUT, max_output=MAX_OUT_BYTES)
    if '-g' in args or result['returncode'] == 0:
        return result
    err_text = result['stderr'].decode('utf-8', errors='replace')
    if 'vkAllocateMemory failed' not in err_text:
        return result
    lines = re.findall(r'\[(\d+)\s+([^\]]+)\]', err_text)
    candidates = []
    for idx, name in lines:
        i = int(idx)
        n = name.lower()
        if 1 <= i <= 7 and not any(x in n for x in ('basic render driver', 'lavapipe', 'llvmpipe', 'software')):
            if i not in candidates:candidates.append(i)
    seen, tried = set(), []
    for gpu_id in candidates[:2]:
        if gpu_id in seen: continue
        seen.add(gpu_id)
        remaining = TIMEOUT - (time.monotonic() - start_time)
        if remaining <= 0: break
        result = execute(exe, args + ['-g', str(gpu_id)], stdin_data=None, cwd=str(cwd), cancel_event=cancel, timeout=remaining, max_output=MAX_OUT_BYTES)
        tried.append(gpu_id)
        if result['returncode'] == 0:
            log = f"GPUを自動で再選択:{gpu_id}\n".encode('utf-8') + result['stderr'][:16384]
            return {'stdout': result['stdout'], 'stderr': log, 'returncode': 0}
    return result
