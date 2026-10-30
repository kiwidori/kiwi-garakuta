"""ABI definitions for the pinned sherpa-onnx 2.0.1 C API."""
import ctypes as c

class SherpaOnnxOfflineTtsVitsModelConfig(c.Structure):
    _fields_ = [
        ('model', c.c_void_p),
        ('lexicon', c.c_void_p),
        ('tokens', c.c_void_p),
        ('data_dir', c.c_void_p),
        ('noise_scale', c.c_float),
        ('noise_scale_w', c.c_float),
        ('length_scale', c.c_float),
        ('dict_dir', c.c_void_p),
    ]

class SherpaOnnxOfflineTtsMatchaModelConfig(c.Structure):
    _fields_ = [
        ('acoustic_model', c.c_void_p),
        ('vocoder', c.c_void_p),
        ('lexicon', c.c_void_p),
        ('tokens', c.c_void_p),
        ('data_dir', c.c_void_p),
        ('noise_scale', c.c_float),
        ('length_scale', c.c_float),
        ('dict_dir', c.c_void_p),
    ]

class SherpaOnnxOfflineTtsKokoroModelConfig(c.Structure):
    _fields_ = [
        ('model', c.c_void_p),
        ('voices', c.c_void_p),
        ('tokens', c.c_void_p),
        ('data_dir', c.c_void_p),
        ('length_scale', c.c_float),
        ('dict_dir', c.c_void_p),
        ('lexicon', c.c_void_p),
        ('lang', c.c_void_p),
    ]

class SherpaOnnxOfflineTtsKittenModelConfig(c.Structure):
    _fields_ = [
        ('model', c.c_void_p),
        ('voices', c.c_void_p),
        ('tokens', c.c_void_p),
        ('data_dir', c.c_void_p),
        ('length_scale', c.c_float),
        ('lexicon', c.c_void_p),
    ]

class SherpaOnnxOfflineTtsZipvoiceModelConfig(c.Structure):
    _fields_ = [
        ('tokens', c.c_void_p),
        ('encoder', c.c_void_p),
        ('decoder', c.c_void_p),
        ('vocoder', c.c_void_p),
        ('data_dir', c.c_void_p),
        ('lexicon', c.c_void_p),
        ('feat_scale', c.c_float),
        ('t_shift', c.c_float),
        ('target_rms', c.c_float),
        ('guidance_scale', c.c_float),
    ]

class SherpaOnnxOfflineTtsPocketModelConfig(c.Structure):
    _fields_ = [
        ('lm_flow', c.c_void_p),
        ('lm_main', c.c_void_p),
        ('encoder', c.c_void_p),
        ('decoder', c.c_void_p),
        ('text_conditioner', c.c_void_p),
        ('vocab_json', c.c_void_p),
        ('token_scores_json', c.c_void_p),
        ('voice_embedding_cache_capacity', c.c_int32),
    ]

class SherpaOnnxOfflineTtsSupertonicModelConfig(c.Structure):
    _fields_ = [
        ('duration_predictor', c.c_void_p),
        ('text_encoder', c.c_void_p),
        ('vector_estimator', c.c_void_p),
        ('vocoder', c.c_void_p),
        ('tts_json', c.c_void_p),
        ('unicode_indexer', c.c_void_p),
        ('voice_style', c.c_void_p),
    ]

class SherpaOnnxOfflineTtsModelConfig(c.Structure):
    _fields_ = [
        ('vits', SherpaOnnxOfflineTtsVitsModelConfig),
        ('num_threads', c.c_int32),
        ('debug', c.c_int32),
        ('provider', c.c_void_p),
        ('matcha', SherpaOnnxOfflineTtsMatchaModelConfig),
        ('kokoro', SherpaOnnxOfflineTtsKokoroModelConfig),
        ('kitten', SherpaOnnxOfflineTtsKittenModelConfig),
        ('zipvoice', SherpaOnnxOfflineTtsZipvoiceModelConfig),
        ('pocket', SherpaOnnxOfflineTtsPocketModelConfig),
        ('supertonic', SherpaOnnxOfflineTtsSupertonicModelConfig),
    ]

class SherpaOnnxOfflineTtsConfig(c.Structure):
    _fields_ = [
        ('model', SherpaOnnxOfflineTtsModelConfig),
        ('rule_fsts', c.c_void_p),
        ('max_num_sentences', c.c_int32),
        ('rule_fars', c.c_void_p),
        ('silence_scale', c.c_float),
    ]

class SherpaOnnxGenerationConfig(c.Structure):
    _fields_ = [
        ('silence_scale', c.c_float),
        ('speed', c.c_float),
        ('sid', c.c_int32),
        ('reference_audio', c.c_void_p),
        ('reference_audio_len', c.c_int32),
        ('reference_sample_rate', c.c_int32),
        ('reference_text', c.c_void_p),
        ('num_steps', c.c_int32),
        ('extra', c.c_void_p),
        ('phoneme_codepoints', c.c_void_p),
        ('phoneme_codepoints_lens', c.c_void_p),
        ('phoneme_codepoints_num_sentences', c.c_int32),
        ('tokens', c.c_void_p),
        ('tokens_lens', c.c_void_p),
        ('tokens_num_sentences', c.c_int32),
    ]

class SherpaOnnxGeneratedAudio(c.Structure):
    _fields_ = [
        ('samples', c.c_void_p),
        ('n', c.c_int32),
        ('sample_rate', c.c_int32),
    ]
