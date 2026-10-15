def safe_duration(total_samples, offset_ms, duration_ms, vad=False, processors=1):
    for v in (total_samples, offset_ms, duration_ms):
        if isinstance(v, bool) or not isinstance(v, int):
            raise ValueError("整数値で指定してください")
    if total_samples <= 0 or total_samples > 57600000:
        raise ValueError("音声を確認してください。空の音声や1時間を超える音声は使えません。")
    total_ms = total_samples // 16
    if offset_ms < 0 or offset_ms >= total_ms:
        raise ValueError("オフセットが範囲外です")
    if duration_ms < 0 or duration_ms > 3600000:
        raise ValueError("再生時間が無効です")
    if vad and (offset_ms != 0 or duration_ms != 0):
        raise ValueError("VAD有効時はオフセット/再生時間指定不可です")
    if processors > 1 and (offset_ms != 0 or duration_ms != 0):
        raise ValueError("CPU分割（processors）時はオフセット/再生時間指定不可です")
    if duration_ms == 0:
        return 0
    eff = min(duration_ms, total_ms - offset_ms)
    if eff <= 0:
        raise ValueError("有効な再生時間がありません")
    return eff
