# transfer.py
MAX_PAYLOAD = 2 * 1024 * 1024


def payload(result, target):
    """
    Validate and return payload string for transfer.
    Only allowed: shfmt+shell->bat, code2prompt+markdown->glow.
    """
    if not isinstance(result, dict):
        raise ValueError("移送できる結果がありません。")
    engine = result.get('engine')
    ttype = result.get('transferable_type')
    rc = result.get('returncode', -1)

    if rc != 0:
        raise ValueError("転送には成功(rc=0)が必要です")

    allowed = {
        ('shfmt', 'shell'): 'bat',
        ('code2prompt', 'markdown'): 'glow',
    }

    key = (engine, ttype)
    if key not in allowed:
        raise ValueError(f"無効な転送組み合わせです: engine={engine}, type={ttype}")

    expected_target = allowed[key]
    if target != expected_target:
        raise ValueError(f"ターゲットが一致しません: 期待{expected_target}, 指定{target}")

    data = result.get('stdout', b'')
    if len(data) > MAX_PAYLOAD:
        raise ValueError("ペイロードが2MiBを超えています")

    try:
        text = data.decode('utf-8')
    except UnicodeDecodeError:
        raise ValueError("出力は厳密なUTF-8でなければなりません")

    if '\x00' in text:
        raise ValueError("ペイロードにNUL文字が含まれています")
    if '\x1b' in text:
        raise ValueError("ペイロードにESCシーケンスが含まれています")

    return text
