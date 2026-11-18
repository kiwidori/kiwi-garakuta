"""Bounded local video sampling; composition is independent of native commands."""
import ctypes
import hashlib
import io
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time

from PIL import Image
from consumer_runtime import Engine, NativeJob, check, safe_path, stage, save_file
from layout import compose

ROOT = Path(sys.executable).parent if getattr(sys, 'frozen', False) else Path(__file__).resolve().parent
ENGINE = Engine(ROOT)
EXTENSIONS = {'.mp4', '.mov', '.mkv', '.webm', '.avi', '.m4v', '.mpg', '.mpeg', '.ts'}
INPUT = ['-protocol_whitelist', 'file', '-format_whitelist', 'mov,matroska,webm,avi,mpegts,mpeg', '-threads', '2']


def settings(values):
    opts = {}
    for name, low, high, default in [('count', 4, 36, 12), ('columns', 2, 6, 4), ('width', 160, 480, 320)]:
        raw = str(values.get(name, default))
        if not raw.isascii() or not raw.isdigit() or not low <= int(raw) <= high:
            label = {'count': '場面数', 'columns': '列数', 'width': 'コマの幅'}[name]
            raise ValueError(f'{label}は{low}～{high}の整数で指定してください。')
        opts[name] = int(raw)
    for name in ['start', 'end']:
        try:
            number = float(values.get(name, 0))
        except (ValueError, TypeError):
            raise ValueError('開始・終了は秒数で指定してください。') from None
        if not math.isfinite(number) or not 0 <= number <= 3600:
            raise ValueError('開始・終了は0～3600秒で指定してください。')
        opts[name] = number
    opts['theme'] = values.get('theme', '明るい')
    if opts['theme'] not in {'明るい', '暗い'}:
        raise ValueError('背景を選んでください。')
    for key in ['show_title', 'show_times']:
        value = values.get(key, True)
        if type(value) is not bool:
            raise ValueError('タイトル・時刻の表示を確認してください。')
        opts[key] = value
    rows = math.ceil(opts['count'] / opts['columns'])
    canvas_w = opts['columns'] * opts['width'] + (opts['columns'] + 1) * 12
    canvas_h = (50 if opts['show_title'] else 0) + rows * (opts['width'] * 9 // 16 + (24 if opts['show_times'] else 0)) + (rows + 1) * 12
    if canvas_w > 4096 or canvas_h > 4096 or canvas_w * canvas_h > 16000000:
        raise ValueError('一覧画像が大きすぎます。場面数やコマの幅を減らすか、列数を増やしてください。')
    return opts


def verify_engine(cancel):
    ENGINE.executable()
    for name, digest in ENGINE.pin['members'].items():
        if not name.lower().endswith(('.dll', '.exe')):
            continue
        p = safe_path(ENGINE.cache / name)
        h = hashlib.sha256()
        with p.open('rb') as f:
            while chunk := f.read(1024**2):
                check(cancel)
                h.update(chunk)
        if h.hexdigest() != digest:
            raise ValueError('動画エンジンの検証に失敗しました。公式版の準備をやり直してください。')


def native(args, work, cancel, probe=False, timeout=30):
    check(cancel)
    name = ENGINE.pin['probe' if probe else 'executable']
    exe = safe_path(ENGINE.cache / name)
    with (work / 'stdout.log').open('wb') as out, (work / 'stderr.log').open('wb') as err:
        group = NativeJob()
        proc = None
        try:
            proc = subprocess.Popen([str(exe), *map(str, args)], cwd=work, stdin=subprocess.DEVNULL,
                                    stdout=out, stderr=err, creationflags=subprocess.CREATE_NO_WINDOW)
            group.attach(proc)
            deadline = time.monotonic() + timeout
            while proc.poll() is None:
                check(cancel)
                if time.monotonic() > deadline:
                    raise ValueError('場面の読み取りに時間がかかりすぎています。短い動画でお試しください。')
                for path in work.iterdir():
                    if path.is_file() and path.name != 'input' + path.suffix.lower() and path.stat().st_size > 32 * 1024**2:
                        raise ValueError('作業ファイルが容量の上限を超えました。')
                time.sleep(.05)
        finally:
            group.close()
            if proc is not None:
                proc.wait(timeout=10)
    check(cancel)
    if (work / 'stdout.log').stat().st_size > 4 * 1024**2 or (work / 'stderr.log').stat().st_size > 4 * 1024**2:
        raise ValueError('動画情報が大きすぎます。')
    if proc.returncode:
        error = (work / 'stderr.log').read_bytes()[-1800:].decode('utf8', 'replace').replace(str(work), '作業フォルダー')
        raise ValueError('動画を読み込めませんでした。\n' + error)
    return (work / 'stdout.log').read_bytes()


def probe(source, work, cancel):
    data = json.loads(native(['-v', 'error', *INPUT, '-show_format', '-show_streams', '-of', 'json', str(source)], work, cancel, probe=True))
    videos = [s for s in data.get('streams', []) if s.get('codec_type') == 'video' and not s.get('disposition', {}).get('attached_pic')]
    if not videos:
        raise ValueError('通常の映像トラックのある動画を選んでください。')
    video = videos[0]
    width, height = video.get('width'), video.get('height')
    if type(width) is not int or type(height) is not int or not 1 <= width <= 4096 or not 1 <= height <= 4096 or width * height > 9000000:
        raise ValueError('入力動画は各辺4096px・900万画素までです。')
    try:
        duration = float(data.get('format', {}).get('duration', video.get('duration', 0)))
    except (ValueError, TypeError):
        duration = 0
    if not math.isfinite(duration) or not .1 <= duration <= 3600:
        raise ValueError('長さを取得できる0.1～3600秒の動画を選んでください。')
    if type(video.get('index')) is not int or not 0 <= video['index'] < 100:
        raise ValueError('映像トラックを確認できません。')
    return duration, video['index']


def font_path():
    buf = ctypes.create_unicode_buffer(32768)
    count = ctypes.windll.kernel32.GetWindowsDirectoryW(buf, len(buf))
    if not 0 < count < len(buf):
        raise OSError('Windowsのフォントを取得できません。')
    font = Path(buf.value) / 'Fonts/meiryo.ttc'
    if not font.is_file():
        raise ValueError('日本語の表示にはWindowsのMeiryoフォントが必要です。')
    return str(font)


def render(path, options, cancel, progress=None):
    opts = settings(options)
    verify_engine(cancel)
    progress = progress or (lambda text: None)
    with tempfile.TemporaryDirectory(prefix='kiwi-video-sheet-') as td:
        work = Path(td)
        source = stage(path, work, cancel, EXTENSIONS, limit=512 * 1024**2)
        duration, track = probe(source, work, cancel)
        start, end = opts['start'], opts['end'] or duration
        if not 0 <= start < end <= duration + .00001:
            raise ValueError('開始・終了を動画の長さ以内で、開始より終了が後になるように指定してください。')
        times = [start + (i + .5) * (end - start) / opts['count'] for i in range(opts['count'])]
        width, height = opts['width'], opts['width'] * 9 // 16
        frames = []
        deadline = time.monotonic() + 600
        for i, timestamp in enumerate(times):
            check(cancel)
            if time.monotonic() >= deadline:
                raise ValueError('全体の処理時間（10分）の上限に達しました。')
            progress(f'場面を読み取り中 {i + 1} / {len(times)}')
            output = work / f'frame-{i:02d}.png'
            vf = f'scale={width}:{height}:force_original_aspect_ratio=decrease:force_divisible_by=2:reset_sar=1,format=rgb24,pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:color=black'
            native(['-hide_banner', '-loglevel', 'error', '-nostdin', *INPUT, '-ss', f'{timestamp:.6f}', '-i', str(source),
                    '-map', f'0:{track}', '-frames:v', '1', '-vf', vf, '-filter_threads', '1', '-threads', '2',
                    '-an', '-sn', '-dn', str(output)], work, cancel, timeout=min(30, max(.1, deadline - time.monotonic())))
            if not output.is_file() or not 0 < output.stat().st_size <= 4 * 1024**2:
                raise ValueError('指定した時刻の画像を取得できません。範囲を少し短くしてください。')
            frames.append(output.read_bytes())
        check(cancel)
        png = compose(frames, times, Path(path).name, opts['columns'], width, opts['theme'], opts['show_title'], opts['show_times'], font_path())
        check(cancel)
        return {'png': png, 'timestamps': times, 'stem': Path(path).stem,
                'text': f'{duration:.1f}秒の動画から{len(times)}場面を抽出しました。\n範囲：{start:.1f}～{end:.1f}秒\n「画像を確認」で仕上がりを見てから保存できます。\n時刻は抽出に指定した位置です。映像のフレーム位置とはわずかに異なる場合があります。'}


def save(result, folder, format, cancel):
    if format not in {'PNG', 'JPEG'} or not isinstance(result, dict):
        raise ValueError('一覧画像と保存形式を確認してください。')
    safe_path(folder, True)
    check(cancel)
    raw = result['png']
    if not isinstance(raw, bytes) or not 0 < len(raw) <= 32 * 1024**2:
        raise ValueError('一覧画像のサイズを確認してください。')
    with tempfile.TemporaryDirectory(prefix='kiwi-video-sheet-save-') as td:
        suffix = '.png' if format == 'PNG' else '.jpg'
        target = Path(td) / ('sheet' + suffix)
        if format == 'PNG':
            target.write_bytes(raw)
        else:
            with Image.open(io.BytesIO(raw)) as image:
                if image.width > 4096 or image.height > 4096 or image.width * image.height > 16000000:
                    raise ValueError('一覧画像が大きすぎます。')
                image.convert('RGB').save(target, 'JPEG', quality=90, optimize=True)
        check(cancel)
        return str(save_file(target, folder, str(result.get('stem', 'video')) + '-一覧', suffix, cancel))
