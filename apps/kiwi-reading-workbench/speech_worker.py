"""UTF-8 C API worker; native inference stays outside the GUI process."""
import array
import ctypes as c
import json
import math
import os
from pathlib import Path
import struct
import sys
import threading
import wave
from speech_abi import SherpaOnnxOfflineTtsConfig as Config, SherpaOnnxGenerationConfig as Generation, SherpaOnnxGeneratedAudio as Audio
from speech_core import options, resources, LIMIT_SECONDS


def run():
    source = Path.cwd() / 'input.json'
    if not source.is_file() or source.stat().st_size > 8192:
        raise ValueError('Input limit')
    payload = source.read_bytes()
    v = options(json.loads(payload))
    output = Path.cwd() / 'speech.wav'
    if output.exists():
        raise ValueError('Output exists')
    engine, model = resources(threading.Event())
    # Relative ASCII model names avoid the Windows CLI's narrow argv conversion.
    os.chdir(model)
    directory = os.add_dll_directory(str(engine / 'lib'))
    lib = c.CDLL(str(engine / 'lib/sherpa-onnx-c-api.dll'))
    lib.SherpaOnnxCreateOfflineTts.argtypes = [c.POINTER(Config)]
    lib.SherpaOnnxCreateOfflineTts.restype = c.c_void_p
    lib.SherpaOnnxDestroyOfflineTts.argtypes = [c.c_void_p]
    lib.SherpaOnnxDestroyOfflineTts.restype = None
    lib.SherpaOnnxOfflineTtsSampleRate.argtypes = [c.c_void_p]
    lib.SherpaOnnxOfflineTtsSampleRate.restype = c.c_int32
    lib.SherpaOnnxOfflineTtsNumSpeakers.argtypes = [c.c_void_p]
    lib.SherpaOnnxOfflineTtsNumSpeakers.restype = c.c_int32
    lib.SherpaOnnxOfflineTtsGenerateWithConfig.argtypes = [c.c_void_p, c.c_char_p, c.POINTER(Generation), c.c_void_p, c.c_void_p]
    lib.SherpaOnnxOfflineTtsGenerateWithConfig.restype = c.POINTER(Audio)
    lib.SherpaOnnxDestroyOfflineTtsGeneratedAudio.argtypes = [c.POINTER(Audio)]
    lib.SherpaOnnxDestroyOfflineTtsGeneratedAudio.restype = None
    keep = []
    def text(value):
        b = c.create_string_buffer(value.encode('utf8'))
        keep.append(b)
        return c.cast(b, c.c_void_p)
    config = Config()
    config.model.num_threads = v['threads']
    config.model.provider = text('cpu')
    config.max_num_sentences = 1
    config.silence_scale = 1
    for field, filename in [('duration_predictor', 'duration_predictor.int8.onnx'), ('text_encoder', 'text_encoder.int8.onnx'), ('vector_estimator', 'vector_estimator.int8.onnx'), ('vocoder', 'vocoder.int8.onnx'), ('tts_json', 'tts.json'), ('unicode_indexer', 'unicode_indexer.bin'), ('voice_style', 'voice.bin')]:
        setattr(config.model.supertonic, field, text(filename))
    gen = Generation()
    gen.speed = v['speed']
    gen.sid = v['speaker']
    gen.num_steps = v['steps']
    gen.silence_scale = 1
    gen.extra = text(json.dumps({'lang': v['lang'], 'silence_duration': v['pause'], 'max_len': v['chunk'], 'seed': v['seed']}))
    handle = lib.SherpaOnnxCreateOfflineTts(c.byref(config))
    if not handle:
        raise ValueError('Engine initialization failed')
    audio = None
    try:
        if lib.SherpaOnnxOfflineTtsSampleRate(handle) != 44100 or lib.SherpaOnnxOfflineTtsNumSpeakers(handle) != 10:
            raise ValueError('Model properties differ')
        (output.parent / 'ready.json').write_text(json.dumps({'pid': os.getpid()}), encoding='utf8')
        audio = lib.SherpaOnnxOfflineTtsGenerateWithConfig(handle, v['text'].encode('utf8'), c.byref(gen), None, None)
        if not audio:
            raise ValueError('No audio')
        value = audio.contents
        if value.sample_rate != 44100 or not value.samples or not 0 < value.n <= value.sample_rate * LIMIT_SECONDS:
            raise ValueError('Audio limit')
        samples = array.array('f')
        samples.frombytes(c.string_at(value.samples, value.n * 4))
        if not all(math.isfinite(x) for x in samples):
            raise ValueError('Invalid audio')
        pcm = array.array('h', (round(max(-1, min(1, x)) * 32767) for x in samples))
        with wave.open(str(output), 'wb') as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(value.sample_rate)
            w.writeframes(pcm.tobytes())
        # Keep a provenance comment in the WAV; users must also disclose when publishing.
        comment = b'Synthetic speech generated with Supertonic 3; OpenRAIL-M license.\0'
        info = b'INFO' + b'ICMT' + struct.pack('<I', len(comment)) + comment + b'\0' * (len(comment) % 2)
        with output.open('r+b') as f:
            f.seek(0, 2)
            f.write(b'LIST' + struct.pack('<I', len(info)) + info)
            length = f.tell()
            f.seek(4)
            f.write(struct.pack('<I', length - 8))
    finally:
        if audio:
            lib.SherpaOnnxDestroyOfflineTtsGeneratedAudio(audio)
        lib.SherpaOnnxDestroyOfflineTts(handle)
        directory.close()
