"""RapidOCR backend wrapper for KiwiOCR."""
import math
import os
from typing import Any, Dict, List

import numpy as np
from PIL import Image

import onnxruntime as ort
ort.disable_telemetry_events()

from rapidocr import RapidOCR
from rapidocr.utils.download_file import DownloadFile


def _block_download(*args: Any, **kwargs: Any) -> None:
    raise RuntimeError("Forbidden auto download")


DownloadFile.run = _block_download  # type: ignore[attr-defined]

_MAX_ROWS = 10_000

# Flat dotted-key defaults (verified against trial/config input).
_DEFAULTS: Dict[str, Any] = {
    "Global.log_level": "error",
    "EngineConfig.onnxruntime.intra_op_num_threads": 4,
    "EngineConfig.onnxruntime.inter_op_num_threads": 1,
    "Rec.lang_type": "japan",
    "Global.max_side_len": 2000,
    "Global.text_score": 0.5,
    "Global.use_det": True,
    "Global.use_cls": True,
    "Global.use_rec": True,
    "Global.use_preprocess_img": True,
    "Global.min_side_len": 30,
    "Global.use_vertical_padding": True,
    "Global.min_height": 30,
    "Global.width_height_ratio": 8,
    "Global.return_word_box": False,
    "Global.return_single_char_box": False,
    "Det.limit_side_len": 736,
    "Det.thresh": 0.3,
    "Det.box_thresh": 0.5,
    "Det.max_candidates": 1000,
    "Det.unclip_ratio": 1.6,
    "Det.use_dilation": True,
    "Det.score_mode": "fast",
    "Cls.cls_thresh": 0.9,
    "Rec.rec_batch_num": 6,
}

# Allowed user-supplied keys -> (kind, lo, hi)
_ALLOWED: Dict[str, tuple] = {
    "text_score": ("float", 0.0, 1.0),
    "use_cls": ("bool", None, None),
    "return_word_box": ("bool", None, None),
    "return_single_char_box": ("bool", None, None),
    "threads": ("int", 1, 16),
    "det_limit_side_len": ("int", 64, 1536),
    "det_thresh": ("float", 0.0, 1.0),
    "det_box_thresh": ("float", 0.0, 1.0),
    "det_unclip_ratio": ("float", 0.5, 3.0),
    "det_max_candidates": ("int", 1, 1000),
    "det_use_dilation": ("bool", None, None),
    "det_score_mode": ("str_enum", ("fast", "slow"), None),
    "rec_batch_num": ("int", 1, 16),
    "cls_thresh": ("float", 0.0, 1.0),
    "use_preprocess_img": ("bool", None, None),
    "use_vertical_padding": ("bool", None, None),
    "min_height": ("int", 1, 100),
    "width_height_ratio": ("float", 1.0, 30.0),
}

# Map user key -> (dotted_key, default)
_KEY_MAP: Dict[str, tuple] = {
    "text_score": ("Global.text_score", 0.5),
    "use_cls": ("Global.use_cls", True),
    "return_word_box": ("Global.return_word_box", False),
    "return_single_char_box": ("Global.return_single_char_box", False),
    "threads": ("EngineConfig.onnxruntime.intra_op_num_threads", 4),
    "det_limit_side_len": ("Det.limit_side_len", 736),
    "det_thresh": ("Det.thresh", 0.3),
    "det_box_thresh": ("Det.box_thresh", 0.5),
    "det_unclip_ratio": ("Det.unclip_ratio", 1.6),
    "det_max_candidates": ("Det.max_candidates", 1000),
    "det_use_dilation": ("Det.use_dilation", True),
    "det_score_mode": ("Det.score_mode", "fast"),
    "rec_batch_num": ("Rec.rec_batch_num", 6),
    "cls_thresh": ("Cls.cls_thresh", 0.9),
    "use_preprocess_img": ("Global.use_preprocess_img", True),
    "use_vertical_padding": ("Global.use_vertical_padding", True),
    "min_height": ("Global.min_height", 30),
    "width_height_ratio": ("Global.width_height_ratio", 8),
}


def _is_finite_number(v: Any) -> bool:
    if isinstance(v, bool):
        return False
    if not isinstance(v, (int, float)):
        return False
    return math.isfinite(v)


def _validate_opts(opts: Dict[str, Any]) -> Dict[str, Any]:
    """Validate only supplied keys; merge all actual defaults. Returns flat dotted-key dict."""
    if not isinstance(opts, dict):
        raise ValueError("opts must be a dict")

    for key in opts:
        if key not in _ALLOWED:
            raise ValueError(f"Unknown option key: {key!r}")

    # Start with all defaults
    params = dict(_DEFAULTS)

    # Apply and validate only supplied keys
    for key, val in opts.items():
        kind, lo, hi = _ALLOWED[key]
        if kind == "bool":
            if not isinstance(val, bool):
                raise ValueError(f"{key} must be bool")
        elif kind == "int":
            if isinstance(val, bool) or not isinstance(val, int):
                raise ValueError(f"{key} must be int")
            if val < lo or val > hi:
                raise ValueError(f"{key} out of range [{lo}, {hi}]")
        elif kind == "float":
            if not _is_finite_number(val):
                raise ValueError(f"{key} must be finite number")
            v = float(val)
            if v < lo or v > hi:
                raise ValueError(f"{key} out of range [{lo}, {hi}]")
            val = v
        elif kind == "str_enum":
            if not isinstance(val, str) or val not in lo:
                raise ValueError(f"{key} must be one of {lo}")

        dotted_key, _ = _KEY_MAP[key]
        params[dotted_key] = val

    # If char boxes requested, force word boxes too.
    if params.get("Global.return_single_char_box"):
        params["Global.return_word_box"] = True

    return params


def _clamp_box(box: Any, w: int, h: int) -> List[List[float]]:
    """Clamp box coordinates to image bounds; raise on non-finite."""
    arr = np.asarray(box, dtype=np.float64)
    if arr.shape != (4, 2):
        raise ValueError(f"Expected box shape (4,2), got {arr.shape}")
    pts: List[List[float]] = []
    for i in range(4):
        x = float(arr[i][0])
        y = float(arr[i][1])
        if not (math.isfinite(x) and math.isfinite(y)):
            raise ValueError("Non-finite box coordinate")
        x = max(0.0, min(float(w), x))
        y = max(0.0, min(float(h), y))
        pts.append([x, y])
    return pts


def _build_params(valid: Dict[str, Any], paths: Dict[str, str]) -> Dict[str, Any]:
    """Build flat dotted-key params dict for RapidOCR 3.10.0."""
    params = dict(valid)

    # Fixed model paths (local, no download).
    params["Det.model_path"] = paths["det"]
    params["Rec.model_path"] = paths["rec"]
    params["Cls.model_path"] = paths["cls"]

    # Fixed engine settings.
    params["EngineConfig.onnxruntime.inter_op_num_threads"] = 1
    params["Global.log_level"] = "error"
    params["Global.max_side_len"] = 2000
    params["Rec.lang_type"] = "japan"

    return params


def recognize(image: Image.Image, mode: str, opts: Dict[str, Any], paths: Dict[str, str]) -> Dict[str, Any]:
    """Run OCR and return JSON-serializable result dict."""
    if mode not in ("full", "detect", "line", "angle"):
        raise ValueError(f"Invalid mode: {mode!r}")

    # Validate before heavy initialization.
    valid = _validate_opts(opts)

    for key in ("det", "rec", "cls"):
        if not os.path.isfile(paths[key]):
            raise FileNotFoundError(f"Model file not found: {paths[key]}")

    w, h = image.size
    bgr = np.array(image.convert("RGB"))[:, :, ::-1].copy()

    params = _build_params(valid, paths)

    # Per-mode explicit flags.
    if mode == "full":
        use_det, use_cls, use_rec = True, valid.get("Global.use_cls", True), True
    elif mode == "detect":
        use_det, use_cls, use_rec = True, False, False
    elif mode == "line":
        use_det, use_cls, use_rec = False, valid.get("Global.use_cls", True), True
    else:  # angle
        use_det, use_cls, use_rec = False, True, False

    ocr = RapidOCR(params=params)
    result = ocr(bgr, use_det=use_det, use_cls=use_cls, use_rec=use_rec)

    rows: List[Dict[str, Any]] = []
    markdown = ""

    if mode == "full":
        boxes = getattr(result, "boxes", None)
        txts = getattr(result, "txts", None)
        scores = getattr(result, "scores", None)
        word_results = getattr(result, "word_results", None)

        n = 0
        if boxes is not None and txts is not None and scores is not None:
            n = len(txts)

        for i in range(min(n, _MAX_ROWS)):
            box_arr = np.asarray(boxes[i], dtype=np.float64)
            score_f = float(scores[i])
            if not math.isfinite(score_f):
                raise ValueError(f"Non-finite score at row {i}")
            text_s = str(txts[i])
            row_box = _clamp_box(box_arr, w, h)

            words: List[Dict[str, Any]] = []

            if word_results is not None and i < len(word_results):
                line_words = word_results[i]
                if line_words is not None:
                    for wr in line_words:
                        if isinstance(wr, tuple) and len(wr) == 3:
                            wt, ws, wb = wr
                            if wt == "" and ws == 1.0 and wb is None:
                                continue
                            if wb is not None:
                                wbox_arr = np.asarray(wb, dtype=np.float64)
                                if wbox_arr.shape != (4, 2):
                                    continue
                                ws_f = float(ws)
                                if not math.isfinite(ws_f):
                                    continue
                                words.append({
                                    "text": str(wt),
                                    "score": ws_f,
                                    "box": _clamp_box(wbox_arr, w, h),
                                })

            rows.append({
                "text": text_s,
                "score": score_f,
                "box": row_box,
                "words": words,
            })

        if rows and hasattr(result, "to_markdown"):
            md = result.to_markdown()
            markdown = str(md) if md is not None else ""
        else:
            markdown = "\n".join(r["text"] for r in rows)

    elif mode == "detect":
        boxes = getattr(result, "boxes", None)
        scores = getattr(result, "scores", None)
        if boxes is not None and scores is not None:
            n = len(boxes)
            for i in range(min(n, _MAX_ROWS)):
                box_arr = np.asarray(boxes[i], dtype=np.float64)
                score_f = float(scores[i])
                if not math.isfinite(score_f):
                    raise ValueError(f"Non-finite score at row {i}")
                rows.append({
                    "text": "",
                    "score": score_f,
                    "box": _clamp_box(box_arr, w, h),
                    "words": [],
                })

    elif mode == "line":
        txts = result.txts or ()
        scores = result.scores
        for i, text in enumerate(txts):
            if i >= _MAX_ROWS:
                break
            score = float(scores[i])
            if math.isfinite(score) and 0.0 <= score <= 1.0:
                rows.append({
                    "text": str(text),
                    "score": score,
                    "box": [[0, 0], [w, 0], [w, h], [0, h]],
                    "words": []
                })
        markdown = "\n".join(row["text"] for row in rows)

    elif mode == "angle":
        cls_res = result.cls_res
        if cls_res is not None and len(cls_res) > 0:
            label, score = cls_res[0]
            label = str(label)
            score = float(score)
            if label in ("0", "180") and math.isfinite(score) and 0.0 <= score <= 1.0:
                rows.append({
                    "text": label + "°",
                    "score": score,
                    "box": [[0, 0], [w, 0], [w, h], [0, h]],
                    "words": []
                })

    return {"rows": rows, "markdown": markdown}
