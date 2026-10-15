def score_export(prefix, enabled):
    if not enabled:
        return {}
    from pathlib import Path
    p = Path(str(prefix) + '.score.txt')
    if not p.is_file() or p.stat().st_size > 16 * 1024 ** 2:
        raise ValueError('invalid score file')
    b = p.read_bytes()
    if len(b) > 16 * 1024 ** 2:
        raise ValueError('score too large')
    return {'score.txt': b}
