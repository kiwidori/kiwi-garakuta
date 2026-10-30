"""Load the fixed qrcp payload from this distribution."""
import hashlib
import json
from pathlib import Path
import tempfile
import threading
import zipfile

from resource_paths import resource_path

_lock = threading.Lock()
_native = None


def native_exe():
    global _native
    with _lock:
        if _native is None:
            base = Path(resource_path('browser-engine', Path(__file__).parent))
            pin = json.loads((base / 'upstream-pin.json').read_text(encoding='utf8'))
            with zipfile.ZipFile(base / 'native-payload.zip') as archive:
                binary = archive.read('qrcp.exe')
            if hashlib.sha256(binary).hexdigest() != pin['native_sha256']:
                raise ValueError('転送用プログラムの検証に失敗しました。ZIPを展開し直してください。')
            work = tempfile.TemporaryDirectory(prefix='kiwi-browser-engine-')
            try:
                (Path(work.name) / 'qrcp.exe').write_bytes(binary)
            except BaseException:
                work.cleanup()
                raise
            _native = work
        return Path(_native.name) / 'qrcp.exe'
