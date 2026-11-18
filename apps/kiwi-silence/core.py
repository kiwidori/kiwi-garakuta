"""Single-source, local-only Auto-Editor jobs with fixed output profiles."""
import ctypes
from ctypes import wintypes
import hashlib
import json
import math
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import time

from consumer_runtime import Engine, NativeJob, check, safe_path, save_file, stage

ROOT = Path(sys.executable).parent if getattr(sys, 'frozen', False) else Path(__file__).resolve().parent
ENGINE = Engine(ROOT)
EXTENSIONS = {'.wav', '.mp3', '.m4a', '.flac', '.ogg', '.aac', '.mp4', '.mov', '.mkv', '.webm', '.avi'}
PROFILES = {'MP4（動画）': ('.mp4', ['-c:v', 'libx264', '-preset', 'fast', '-pix_fmt', 'yuv420p', '-c:a', 'aac']),
            'WAV（音声）': ('.wav', ['-vn', '-c:a', 'pcm_s16le']),
            'MP3（音声）': ('.mp3', ['-vn', '-c:a', 'libmp3lame', '-b:a', '192k'])}


def number(value, low, high, label):
    try:
        n = float(value)
    except (TypeError, ValueError):
        raise ValueError(label + 'は数値で指定してください。') from None
    if not math.isfinite(n) or not low <= n <= high:
        raise ValueError(f'{label}は{low}～{high}の範囲で指定してください。')
    return n


def settings(values):
    result = {}
    for key, low, high, label, default in [
        ('threshold', .01, 50, '無音のしきい値', 4), ('before', 0, 5, '前の余白', .2),
        ('after', 0, 5, '後の余白', .2), ('mincut', 0, 30, '最短の無音', .2),
        ('minclip', 0, 30, '最短の発話', .1), ('speed', .5, 3, '通常部分の速度', 1),
        ('silent_speed', 2, 20, '無音の早送り速度', 5), ('crf', 16, 32, '動画の画質値', 23)]:
        result[key] = number(values.get(key, default), low, high, label)
    for key, choices, default in [('profile', PROFILES, 'MP4（動画）'),
                                  ('silent', ['カットする', '早送りする'], 'カットする'),
                                  ('normalize', ['変更しない', 'peak', 'ebu'], '変更しない'),
                                  ('layout', ['元のまま', 'mono', 'stereo'], '元のまま')]:
        value = values.get(key, default)
        if value not in choices:
            raise ValueError('出力・音声の設定を選んでください。')
        result[key] = value
    stream = str(values.get('stream', 'all'))
    if stream != 'all' and not re.fullmatch(r'[0-9]', stream):
        raise ValueError('音声トラックはallまたは0～9で指定してください。')
    result['stream'] = stream
    result['ranges'] = []
    text = values.get('ranges', '').strip()
    if len(text) > 2000 or len(text.splitlines()) > 30:
        raise ValueError('指定区間は30行までです。')
    for line in text.splitlines():
        parts = [p.strip() for p in line.split(',')]
        if len(parts) != 3 or parts[0] not in {'残す', '削除'}:
            raise ValueError('区間は「残す,開始秒,終了秒」か「削除,開始秒,終了秒」で指定してください。')
        start = number(parts[1], 0, 3600, '開始秒')
        end = number(parts[2], 0, 3600, '終了秒')
        if start >= end:
            raise ValueError('終了秒は開始秒より後にしてください。')
        result['ranges'].append((parts[0], start, end))
    # Overlapping overrides would depend on upstream flag ordering; reject ambiguity.
    ordered = sorted(result['ranges'], key=lambda r: r[1])
    if any(a[2] > b[1] for a, b in zip(ordered, ordered[1:])):
        raise ValueError('指定区間を重ねずに指定してください。')
    return result


def clean_text(raw):
    text = raw.decode('utf8', 'replace')
    return re.sub(r'\x1b\[[0-?]*[ -/]*[@-~]', '', text).replace('\r', '').strip()


def media_job():
    # Video encoders need more working memory than the small text tools.
    class Basic(ctypes.Structure):
        _fields_ = [('process_time', ctypes.c_int64), ('job_time', ctypes.c_int64),
                    ('flags', wintypes.DWORD), ('min_ws', ctypes.c_size_t), ('max_ws', ctypes.c_size_t),
                    ('active', wintypes.DWORD), ('affinity', ctypes.c_size_t),
                    ('priority', wintypes.DWORD), ('scheduling', wintypes.DWORD)]
    class Extended(ctypes.Structure):
        _fields_ = [('basic', Basic), ('io', ctypes.c_uint64 * 6),
                    ('process_memory', ctypes.c_size_t), ('job_memory', ctypes.c_size_t),
                    ('peak_process', ctypes.c_size_t), ('peak_job', ctypes.c_size_t)]
    group = NativeJob()
    info = Extended()
    info.basic.flags = 0x2000 | 0x100 | 0x200
    info.process_memory = info.job_memory = 2 * 1024**3
    if not group.api.SetInformationJobObject(group.handle, 9, ctypes.byref(info), ctypes.sizeof(info)):
        group.close()
        raise OSError('動画処理の実行上限を設定できません。')
    return group


def call(args, work, cancel, timeout=900):
    check(cancel)
    exe = ENGINE.executable()
    if hashlib.sha256(exe.read_bytes()).hexdigest() != ENGINE.pin['sha256']:
        raise ValueError('公式エンジンの検証に失敗しました。保存先のエンジンを削除して準備し直してください。')
    env = {k: v for k, v in os.environ.items() if not k.upper().startswith('AE_')}
    with (work / 'stdout.log').open('wb') as out, (work / 'stderr.log').open('wb') as err:
        group = media_job()
        proc = None
        try:
            proc = subprocess.Popen([str(exe), *map(str, args)], cwd=work, env=env,
                                    stdin=subprocess.DEVNULL, stdout=out, stderr=err,
                                    creationflags=subprocess.CREATE_NO_WINDOW)
            group.attach(proc)
            deadline = time.monotonic() + timeout
            while proc.poll() is None:
                check(cancel)
                if time.monotonic() > deadline:
                    raise ValueError('処理時間の上限（15分）に達しました。短い録音でお試しください。')
                check_sizes(work)
                time.sleep(.08)
        finally:
            group.close()
            if proc is not None:
                proc.wait(timeout=10)
    check(cancel)
    check_sizes(work)
    if proc.returncode:
        error = clean_text((work / 'stderr.log').read_bytes()[-2500:]).replace(str(work), '作業フォルダー')
        raise ValueError('処理できませんでした。入力と設定を確認してください。\n' + error)
    return (work / 'stdout.log').read_bytes()


def check_sizes(work):
    sizes = [p.stat().st_size for p in work.rglob('*') if p.is_file()]
    if any(n > 512 * 1024**2 for n in sizes) or sum(sizes) > 1536 * 1024**2:
        raise ValueError('作業ファイルの容量上限を超えました。')


def info(source, work, cancel):
    raw = call(['info', str(source), '--json'], work, cancel, timeout=60)
    data = json.loads(raw)
    value = data.get(str(source))
    if not isinstance(value, dict) or not value.get('audio'):
        raise ValueError('音声トラックのある動画・音声を選んでください。')
    duration = value.get('container', {}).get('duration', 0)
    number(duration, .01, 3600, '入力の長さ（秒）')
    for video in value.get('video', []):
        resolution = video.get('resolution', [])
        if not isinstance(resolution, list) or len(resolution) != 2 or any(type(n) is not int or n <= 0 for n in resolution):
            raise ValueError('動画の解像度を確認できません。')
        width, height = resolution
        if max(width, height) > 1920 or min(width, height) > 1080:
            raise ValueError('動画はフルHD（長辺1920・短辺1080）までです。')
    return value


def arguments(source, opts, metadata):
    if opts['stream'] != 'all' and int(opts['stream']) >= len(metadata['audio']):
        raise ValueError('指定した音声トラックがありません。allまたは存在する番号を選んでください。')
    args = [str(source), '--edit', f"audio:threshold={opts['threshold']:g}%,stream={opts['stream']}",
            '--margin', f"{opts['before']:g}s,{opts['after']:g}s", '--smooth',
            f"{opts['mincut']:g}s,{opts['minclip']:g}s", '--when-active', f"speed:{opts['speed']:g}",
            '--when-inactive', 'cut' if opts['silent'] == 'カットする' else f"speed:{opts['silent_speed']:g}",
            '--no-open', '--no-cache', '--progress', 'none']
    for action, start, end in opts['ranges']:
        if end > metadata['container']['duration']:
            raise ValueError('指定区間が入力の長さを超えています。')
        args.extend(['--keep' if action == '残す' else '--cut', f'{start:g}s,{end:g}s'])
    return args


def preview_text(raw):
    text = clean_text(raw)
    names = {'length:': '長さ:', 'input:': '元の長さ:', 'output:': '保存後の長さ:', 'diff:': '変化:',
             'clips:': '残る区間:', 'cuts:': '除く区間:', 'amount:': '区間数:',
             'smallest:': '最短:', 'largest:': '最長:', 'median:': '中央値:', 'average:': '平均:'}
    for old, new in names.items():
        text = text.replace(old, new)
    return text


def run(input_path, values, cancel, folder=None):
    opts = settings(values)
    if folder is not None:
        safe_path(folder, True)
    with tempfile.TemporaryDirectory(prefix='kiwi-silence-') as td:
        work = Path(td)
        source = stage(input_path, work, cancel, EXTENSIONS, limit=512 * 1024**2)
        metadata = info(source, work, cancel)
        args = arguments(source, opts, metadata)
        report = call([*args, '--preview'], work, cancel)
        match = re.search(r'output:\s*\S+\s+\((\d+)\)', clean_text(report))
        if not match or int(match.group(1)) == 0:
            raise ValueError('残る音声がありません。しきい値を下げるか、残す区間を指定してください。')
        summary = preview_text(report)
        if folder is None:
            return {'text': summary, 'saved': None}
        suffix, profile = PROFILES[opts['profile']]
        if suffix == '.mp4' and not metadata.get('video'):
            raise ValueError('音声のみの入力はWAVまたはMP3で保存してください。')
        output = work / ('output' + suffix)
        render = [*args, '-o', str(output), *profile, '-sn', '-dn']
        if suffix == '.mp4':
            render.extend(['-crf', f"{opts['crf']:g}"])
        if opts['normalize'] != '変更しない':
            render.extend(['--audio-normalize', opts['normalize']])
        if opts['layout'] != '元のまま':
            render.extend(['--audio-layout', opts['layout']])
        call(render, work, cancel)
        if not output.is_file() or not output.stat().st_size:
            raise ValueError('出力ファイルを確認できませんでした。')
        saved = save_file(output, folder, Path(input_path).stem + '-無音カット', suffix, cancel)
        return {'text': summary + '\n\n保存しました：\n' + str(saved), 'saved': str(saved)}
