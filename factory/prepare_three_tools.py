"""Fetch hash-pinned official binaries for the three Windows verifier workflows."""
import hashlib
import io
import json
from pathlib import Path
import sys
import zipfile

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'apps/common'))
from portable_build import fetch


def prepare(slug):
    pin=json.loads((ROOT/'apps'/slug/'upstream-pin.json').read_text(encoding='utf8'))
    target=ROOT/'.tools'/slug/pin['exe']
    if not target.is_file():
        asset=fetch(pin['url'],pin['sha'])
        data=zipfile.ZipFile(io.BytesIO(asset)).read(pin['exe']) if pin['asset'].endswith('.zip') else asset
        target.parent.mkdir(parents=True,exist_ok=True)
        target.write_bytes(data)
    if hashlib.sha256(target.read_bytes()).hexdigest()!=pin['binary_sha']:
        raise ValueError('Cached upstream binary differs from the pinned release')
    return target


if __name__=='__main__':
    for slug in ('kiwi-count','kiwi-shell','kiwi-minify'):
        prepare(slug)
        print('Verified official binary:',slug)
