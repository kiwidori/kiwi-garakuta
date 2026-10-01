"""Build a portable Windows GUI ZIP from a pinned official oxipng release."""

from __future__ import annotations

import hashlib
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
VERSION = "0.1.0"
OXIPNG_VERSION = "10.2.1"
OXIPNG_SHA256 = "7e940f83ee46874b73f53031f96a15834cb70b220af27391fb06fe7b4dd798e1"
OXIPNG_URL = (f"https://github.com/oxipng/oxipng/releases/download/v{OXIPNG_VERSION}/"
                f"oxipng-{OXIPNG_VERSION}-x86_64-pc-windows-msvc.zip")


def main() -> None:
    if os.name != "nt":
        raise SystemExit("Build this release on Windows.")
    request = urllib.request.Request(OXIPNG_URL, headers={"User-Agent": "kiwi-garakuta-build/0.1"})
    with urllib.request.urlopen(request, timeout=45) as response:
        data = response.read()
    digest = hashlib.sha256(data).hexdigest()
    if digest != OXIPNG_SHA256:
        raise SystemExit(f"oxipng SHA-256 mismatch: {digest}")

    with tempfile.TemporaryDirectory(prefix="kiwi-png-") as temp:
        temp_path = Path(temp)
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            for name in ("oxipng.exe", "LICENSE", "README.md"):
                (temp_path / name).write_bytes(archive.read(f"oxipng-{OXIPNG_VERSION}-x86_64-pc-windows-msvc/{'LICENSE.txt' if name == 'LICENSE' else name}"))
        subprocess.run([
            sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--onefile",
            "--noconsole", "--name", "KiwiPNG", "--distpath", str(temp_path / "dist"),
            "--workpath", str(temp_path / "build"), "--specpath", str(temp_path),
            "--add-binary", f"{temp_path / 'oxipng.exe'}{os.pathsep}.", str(ROOT / "main.py"),
        ], check=True)
        release = ROOT / "release"
        if release.resolve().parent != ROOT.resolve() or release.is_symlink():
            raise ValueError("Release path is outside the app directory")
        if release.exists():
            shutil.rmtree(release)
        release.mkdir()
        shutil.copy2(temp_path / "dist" / "KiwiPNG.exe", release / "KiwiPNG.exe")
        shutil.copy2(temp_path / "LICENSE", release / "oxipng-LICENSE")
        shutil.copy2(temp_path / "README.md", release / "oxipng-README.md")
        shutil.copy2(ROOT / "README.txt", release / "README.txt")
        shutil.copy2(ROOT.parents[1] / "LICENSE", release / "LICENSE")

    output = ROOT / f"KiwiPNG-{VERSION}-win11-x64.zip"
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for file in sorted(release.iterdir()):
            archive.write(file, file.name)
    print(f"Built {output} ({output.stat().st_size:,} bytes)")
    print(f"SHA-256: {hashlib.sha256(output.read_bytes()).hexdigest()}")


if __name__ == "__main__":
    main()
