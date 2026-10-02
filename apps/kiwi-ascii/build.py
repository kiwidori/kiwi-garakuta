"""Build a portable Windows GUI ZIP from a pinned official ascii-image-converter release."""

from __future__ import annotations

import hashlib
import importlib.metadata
import io
import os
import shutil
import subprocess
import sys
import tempfile
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
VERSION = "0.2.1"
ASCII_VERSION = "1.13.1"
ASCII_SHA256 = "f1695fe93fafaf44b23ccc8470a4cdd4f60dba4ec8d04be5c17bffc7c8324e9b"
ASCII_URL = (f"https://github.com/TheZoraiz/ascii-image-converter/releases/download/v{ASCII_VERSION}/"
                "ascii-image-converter_Windows_amd64_64bit.zip")


def main() -> None:
    if os.name != "nt":
        raise SystemExit("Build this release on Windows.")
    request = urllib.request.Request(ASCII_URL, headers={"User-Agent": "kiwi-garakuta-build/0.1"})
    with urllib.request.urlopen(request, timeout=45) as response:
        data = response.read()
    digest = hashlib.sha256(data).hexdigest()
    if digest != ASCII_SHA256:
        raise SystemExit(f"ascii-image-converter SHA-256 mismatch: {digest}")

    with tempfile.TemporaryDirectory(prefix="kiwi-ascii-") as temp:
        temp_path = Path(temp)
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            for name in ("ascii-image-converter.exe", "LICENSE.txt", "README.md"):
                (temp_path / name).write_bytes(archive.read(f"ascii-image-converter_Windows_amd64_64bit/{name}"))
        subprocess.run([
            sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--onefile",
            "--noconsole", "--paths", str(ROOT.parents[0] / "common"),
            "--add-data", f"{ROOT / 'advanced-spec.json'}{os.pathsep}.",
            "--add-data", f"{ROOT / 'upstream-help.txt'}{os.pathsep}.", "--name", "KiwiASCII", "--distpath", str(temp_path / "dist"),
            "--exclude-module", "numpy", "--exclude-module", "matplotlib",
            "--exclude-module", "IPython", "--exclude-module", "olefile",
            "--workpath", str(temp_path / "build"), "--specpath", str(temp_path),
            "--add-binary", f"{temp_path / 'ascii-image-converter.exe'}{os.pathsep}.", str(ROOT / "main.py"),
        ], check=True)
        release = ROOT / "release"
        if release.resolve().parent != ROOT.resolve() or release.is_symlink():
            raise ValueError("Release path is outside the app directory")
        if release.exists():
            shutil.rmtree(release)
        release.mkdir()
        shutil.copy2(temp_path / "dist" / "KiwiASCII.exe", release / "KiwiASCII.exe")
        for name in ("LICENSE.txt",):
            shutil.copy2(temp_path / name, release / f"ascii-image-converter-{name}")
        shutil.copy2(temp_path / "README.md", release / "ascii-image-converter-README.md")
        shutil.copy2(ROOT / "README.txt", release / "README.txt")
        shutil.copy2(ROOT / "THIRD-PARTY-NOTICES.txt", release / "THIRD-PARTY-NOTICES.txt")
        pillow = importlib.metadata.distribution('Pillow')
        notices = [pillow.locate_file(f) for f in pillow.files if str(f).endswith('licenses/LICENSE')]
        if len(notices) != 1:
            raise ValueError('Pillow license document missing')
        shutil.copy2(notices[0], release / 'Pillow-LICENSE.txt')
        runtime_notices = []
        for title, path in [('Python', Path(sys.base_prefix)/'LICENSE.txt'), ('Tk', Path(sys.base_prefix)/'tcl'/'tk8.6'/'license.terms')]:
            if not path.is_file():
                raise ValueError(f'{title} runtime license document missing')
            runtime_notices.append(f'=== {title} runtime ===\n'+path.read_text(encoding='utf-8'))
        (release/'Runtime-LICENSES.txt').write_text('\n\n'.join(runtime_notices),encoding='utf-8')
        shutil.copy2(ROOT.parents[1] / "LICENSE", release / "LICENSE")

    output = ROOT / f"KiwiASCII-{VERSION}-win11-x64.zip"
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for file in sorted(release.iterdir()):
            archive.write(file, file.name)
    print(f"Built {output} ({output.stat().st_size:,} bytes)")
    print(f"SHA-256: {hashlib.sha256(output.read_bytes()).hexdigest()}")


if __name__ == "__main__":
    main()
