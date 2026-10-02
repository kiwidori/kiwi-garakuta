"""Build using the hash-pinned official Windows amd64 tar archive."""
import sys,io,tarfile,hashlib,json
from pathlib import Path
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT.parent/'common'))
import portable_build
original_fetch=portable_build.fetch
def fetch(url,sha):
    data=original_fetch(url,sha)
    if url.endswith('.tar.gz'):
        with tarfile.open(fileobj=io.BytesIO(data),mode='r:gz') as archive:
            data=archive.extractfile('yamlfmt.exe').read()
        pin=json.loads((ROOT/'upstream-pin.json').read_text(encoding='utf8'))
        if hashlib.sha256(data).hexdigest()!=pin['binary_sha']:raise ValueError('Binary SHA mismatch')
    return data
if __name__=='__main__':
    import importlib.metadata
    if importlib.metadata.version('PyYAML')!='6.0.3':raise ValueError('Install pinned PyYAML 6.0.3 before building.')
    portable_build.fetch=fetch
    portable_build.build(ROOT)
