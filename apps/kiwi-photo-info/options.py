"""Parse named metadata assignments without accepting CLI options."""
import re

_TAG_RE = re.compile(r'(?:EXIF|IPTC|XMP(?:-[A-Za-z0-9]+)?):[A-Za-z][A-Za-z0-9-]{0,79}\Z')


def parse_extra(text):
    lines = text.split('\n')
    if lines and lines[-1] == '':
        lines.pop()
    if len(lines) > 20:
        raise ValueError('追加タグは最大20行です。')
    result = {}
    seen = set()
    for line in lines:
        if not line:
            continue
        if '=' not in line:
            raise ValueError('追加タグは グループ:タグ=値 の形式で指定してください。')
        tag, value = line.split('=', 1)
        if not _TAG_RE.fullmatch(tag):
            raise ValueError('EXIF・IPTC・XMPのタグ名を指定してください。任意のCLIオプションは使えません。')
        if len(value) > 4096 or any(c in value for c in '\x00\r'):
            raise ValueError('値は改行なしの4096文字以内です。')
        if tag.lower() in seen:
            raise ValueError('追加タグが重複しています：'+tag)
        seen.add(tag.lower())
        result[tag] = value
    return result
