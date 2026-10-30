"""Validate browser uploads before passing normalized names to native qrcp."""
from email import policy
from email.parser import BytesParser
import hashlib
from pathlib import Path
import re
import secrets

MAX_BODY = 32 * 1024**2
MAX_FILES = 20
RESERVED = {'CON', 'PRN', 'AUX', 'NUL', 'CLOCK$', 'CONIN$', 'CONOUT$',
            *(f'{p}{n}' for p in ('COM', 'LPT') for n in '123456789¹²³')}


def filename(value):
    if (not isinstance(value, str) or not value or value[-1:] in ('.', ' ')
            or any(ord(c) < 32 or c in '<>:"/\\|?*\x7f' for c in value)
            or len(value.encode('utf-16-le', errors='surrogatepass')) > 240 * 2
            or value.split('.')[0].rstrip(' ').upper() in RESERVED
            or value in ('.', '..')):
        raise ValueError('使えないファイル名です。名前を変更して送ってください。')
    # Reject lone surrogates, never normalize a name into an existing filename.
    value.encode('utf8')
    return value


def parse_upload(content_type, data):
    if not isinstance(data, bytes) or not 0 < len(data) <= MAX_BODY:
        raise ValueError('1回の送信は32 MiB以下です。')
    if (not isinstance(content_type, str) or len(content_type) > 256
            or '\r' in content_type or '\n' in content_type
            or not content_type.lower().startswith('multipart/form-data;')):
        raise ValueError('ファイル送信の形式が違います。')
    message = BytesParser(policy=policy.default).parsebytes(
        b'Content-Type: ' + content_type.encode('ascii') + b'\r\n\r\n', headersonly=True)
    boundary = message.get_boundary()
    if (message.defects or getattr(message.get('Content-Type'), 'defects', ())
            or message.get_content_type() != 'multipart/form-data' or not boundary
            or not re.fullmatch(r"[A-Za-z0-9'()+_,./:=?\-]{1,70}", boundary)):
        raise ValueError('ファイル送信を読み取れません。')
    marker = b'--' + boundary.encode('ascii')
    if not data.startswith(marker + b'\r\n'):
        raise ValueError('ファイル送信の先頭が違います。')
    # Split at most 21 times, and parse headers only. Never recursively build an
    # untrusted multipart tree before applying the file-count/header limits.
    pieces = data[len(marker) + 2:].split(b'\r\n' + marker, MAX_FILES + 1)
    if len(pieces) < 2 or len(pieces) > MAX_FILES + 1 or pieces[-1] not in (b'--', b'--\r\n'):
        raise ValueError('1回に送れるのは20ファイルまでです。送信内容も確認してください。')
    files = []
    used = set()
    for i, piece in enumerate(pieces[:-1]):
        if i:
            if not piece.startswith(b'\r\n'):
                raise ValueError('ファイルの区切りが違います。')
            piece = piece[2:]
        raw_header, separator, payload = piece.partition(b'\r\n\r\n')
        if not separator or len(raw_header) > 8192:
            raise ValueError('ファイルのヘッダーを読み取れません。')
        part = BytesParser(policy=policy.default).parsebytes(raw_header + b'\r\n\r\n', headersonly=True)
        if (part.get_content_maintype() == 'multipart' or part.defects
                or part.get_content_disposition() != 'form-data'):
            raise ValueError('対応していない送信内容です。')
        # Duplicate MIME headers and encoding transforms are not accepted.
        for header in ('Content-Disposition', 'Content-Type'):
            if len(part.get_all(header, [])) > 1:
                raise ValueError('送信内容のヘッダーが重複しています。')
            if getattr(part.get(header), 'defects', ()):
                raise ValueError('送信内容のヘッダーを読み取れません。')
        if part.get('Content-Transfer-Encoding') is not None:
            raise ValueError('エンコード済みの添付には対応していません。')
        if part.get_param('name', header='content-disposition') != 'files':
            raise ValueError('ファイル以外のフォーム項目は送れません。')
        # get_filename() strips whitespace; validate the decoded parameter itself.
        name = filename(part.get_param('filename', header='content-disposition'))
        folded = name.casefold()
        if folded in used:
            raise ValueError('同じ名前のファイルは分けて送ってください。')
        used.add(folded)
        files.append((name, payload))
        if len(files) > MAX_FILES:
            raise ValueError('1回に送れるのは20ファイルまでです。')
    if not files:
        raise ValueError('送るファイルを選んでください。')
    return files


def native_body(files):
    """User filenames never reach native filesystem calls or MIME headers."""
    boundary = 'kiwi-' + secrets.token_hex(24)
    chunks = []
    records = []
    for name, data in files:
        filename(name)
        internal = secrets.token_hex(24) + '.bin'
        chunks.append((f'--{boundary}\r\nContent-Disposition: form-data; name="files"; '
                       f'filename="{internal}"\r\nContent-Type: application/octet-stream\r\n\r\n').encode())
        chunks.extend((data, b'\r\n'))
        records.append({'name': name, 'internal': internal, 'size': len(data),
                        'sha256': hashlib.sha256(data).hexdigest()})
    chunks.append(f'--{boundary}--\r\n'.encode())
    return 'multipart/form-data; boundary=' + boundary, b''.join(chunks), records


def verified_files(folder, records):
    """Check only expected regular native outputs before any destination commit."""
    folder = Path(folder)
    output = []
    for row in records:
        if not re.fullmatch(r'[a-f0-9]{48}\.bin', row['internal']):
            raise ValueError('受信内容の検証に失敗しました。')
        path = folder / row['internal']
        if path.is_symlink() or path.is_junction() or not path.is_file():
            raise ValueError('受信ファイルが見つかりません。')
        data = path.read_bytes()
        if len(data) != row['size'] or hashlib.sha256(data).hexdigest() != row['sha256']:
            raise ValueError('受信ファイルの内容が一致しません。')
        output.append((filename(row['name']), data))
    return output
