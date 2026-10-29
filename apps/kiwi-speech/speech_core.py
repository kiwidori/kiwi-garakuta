"""Bounded local speech synthesis with pinned engine and voice resources."""
import ctypes
import hashlib
import json
import math
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unicodedata
import wave
from consumer_runtime import Engine, NativeJob, check, safe_path, save_file

ROOT = Path(sys.executable).parent if getattr(sys, 'frozen', False) else Path(__file__).resolve().parent
LANGUAGES = ['ja', 'en', 'ko', 'ar', 'bg', 'cs', 'da', 'de', 'el', 'es', 'et', 'fi', 'fr', 'hi', 'hr', 'hu', 'id', 'it', 'lt', 'lv', 'nl', 'pl', 'pt', 'ro', 'ru', 'sk', 'sl', 'sv', 'tr', 'uk', 'vi']
MODEL_TOP = 'sherpa-onnx-supertonic-3-tts-int8-2026-05-11'
ENGINE_TOP = 'sherpa-onnx-v2.0.1-win-x64-shared-MT-Release'
LIMIT_SECONDS = 90


def options(v):
    if set(v) != {'text', 'lang', 'speaker', 'speed', 'steps', 'threads', 'pause', 'chunk', 'seed'}:
        raise ValueError('設定の項目を確認してください。')
    text = v['text']
    if not isinstance(text, str) or not text.strip() or len(text) > 300:
        raise ValueError('本文は空白だけにせず、300文字以内で入力してください。')
    if any(unicodedata.category(c) in ('Cs', 'Cc') and c not in '\r\n\t' for c in text):
        raise ValueError('本文に使えない制御文字が含まれています。')
    text.encode('utf8')
    if v['lang'] not in LANGUAGES:
        raise ValueError('言語を選んでください。')
    try:
        speaker, steps, threads = (int(v[k]) for k in ('speaker', 'steps', 'threads'))
        speed = float(v['speed'])
        pause = float(v['pause'])
        chunk, seed = (int(v[k]) for k in ('chunk', 'seed'))
    except (ValueError, TypeError, OverflowError) as error:
        raise ValueError('声・速度・品質・CPUの設定を確認してください。') from error
    if not 0 <= speaker <= 9 or not 2 <= steps <= 16 or not 1 <= threads <= 4 or not math.isfinite(speed) or not .5 <= speed <= 2:
        raise ValueError('声0〜9・速度0.5〜2・品質2〜16・CPU1〜4を指定してください。')
    if not math.isfinite(pause) or not 0 <= pause <= 2 or not 20 <= chunk <= 300 or not -1 <= seed <= 2147483647:
        raise ValueError('区切り間の無音0〜2秒・区切り20〜300・乱数-1〜2147483647を指定してください。')
    return dict(text=text, lang=v['lang'], speaker=speaker, steps=steps, threads=threads, speed=speed, pause=pause, chunk=chunk, seed=seed)


def resources(cancel, progress=lambda _: None):
    engines = [Engine(ROOT / name) for name in ('engine', 'voice')]
    for engine in engines:
        for name, digest in engine.pin['members'].items():
            check(cancel)
            path = safe_path(engine.cache / name)
            if not path.is_file():
                raise ValueError('先にエンジンと音声モデルを準備してください。')
            h = hashlib.sha256()
            with path.open('rb') as f:
                while chunk := f.read(1024 * 1024):
                    check(cancel)
                    h.update(chunk)
            if h.hexdigest() != digest:
                raise ValueError('準備済みファイルの検証に失敗しました。')
    return engines[0].cache / ENGINE_TOP, engines[1].cache / MODEL_TOP


def install(cancel, progress):
    import shutil
    if shutil.disk_usage(tempfile.gettempdir()).free < 1024**3:
        raise ValueError('準備には1 GiB以上の空き領域が必要です。')
    for name, label in [('engine', 'エンジン'), ('voice', '音声モデル')]:
        progress(label + 'を準備しています。')
        Engine(ROOT / name).install(cancel, progress)
    resources(cancel)
    return True


def validate_wave(path):
    if path.stat().st_size > 9 * 1024**2:
        raise ValueError('音声のサイズ上限を超えました。')
    with wave.open(str(path)) as w:
        if w.getcomptype() != 'NONE' or w.getnchannels() != 1 or w.getsampwidth() != 2 or w.getframerate() != 44100 or not 0 < w.getnframes() <= w.getframerate() * LIMIT_SECONDS:
            raise ValueError('音声の形式・長さが想定と異なります。')
        return w.getnframes() / w.getframerate()


def generate(v, destination, cancel, progress=lambda _: None):
    v = options(v)
    destination = safe_path(destination, directory=True)
    check(cancel)
    with tempfile.TemporaryDirectory(prefix='kiwi-speech-') as td:
        work = Path(td)
        (work / 'input.json').write_text(json.dumps(v, ensure_ascii=False), encoding='utf8')
        command = [sys.executable]
        if not getattr(sys, 'frozen', False):
            command.append(str(ROOT / 'main.py'))
        command.append('--speech-worker')
        progress('準備済みファイルを確認しています…')
        job = NativeJob()
        with (work / 'input.json').open('rb') as inp, (work / 'stdout.log').open('wb') as out, (work / 'stderr.log').open('wb') as err:
            try:
                # Assign the one-file launcher before it can create its worker child.
                proc = subprocess.Popen(command, cwd=work, stdin=inp, stdout=out, stderr=err, creationflags=subprocess.CREATE_NO_WINDOW | 0x4)
                job.attach(proc)
                resume = ctypes.WinDLL('ntdll').NtResumeProcess
                resume.argtypes = [ctypes.c_void_p]
                resume.restype = ctypes.c_long
                if resume(int(proc._handle)) < 0:
                    raise OSError('音声処理を開始できません。')
                end = time.monotonic() + 90
                ready = False
                while proc.poll() is None:
                    check(cancel)
                    if not ready and (work / 'ready.json').is_file():
                        ready = True
                        progress('文章を読み上げ音声にしています…')
                    if time.monotonic() > end:
                        raise ValueError('処理が90秒を超えました。本文を短くしてください。')
                    if out.tell() > 1024**2 or err.tell() > 1024**2 or sum(p.stat().st_size for p in work.iterdir() if p.is_file()) > 12 * 1024**2:
                        raise ValueError('出力サイズの上限を超えました。')
                    time.sleep(.05)
            finally:
                job.close()
                if 'proc' in locals():
                    proc.wait(timeout=10)
        check(cancel)
        if proc.returncode:
            raise ValueError('音声を作成できませんでした。本文や設定、準備済みファイルを確認してください。')
        seconds = validate_wave(work / 'speech.wav')
        check(cancel)
        saved = save_file(work / 'speech.wav', destination, '読み上げ', '.wav', cancel)
        return {'path': str(saved), 'seconds': seconds, 'lang': v['lang'], 'speaker': v['speaker']}
