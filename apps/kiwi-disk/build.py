"""Build a Windows portable GUI ZIP from a pinned official dust release."""

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
VERSION = "0.2.1"
DUST_VERSION = "1.2.6"
DUST_SHA256 = "d26ad8dab783653ab6a6c0ddf4671fae150be005834f2e3a36a3ac87fb60b7c1"
DUST_URL = (f"https://github.com/bootandy/dust/releases/download/v{DUST_VERSION}/"
            f"dust-v{DUST_VERSION}-x86_64-pc-windows-gnu.zip")


def main() -> None:
    if os.name != "nt":
        raise SystemExit("Build this release on Windows.")
    request = urllib.request.Request(DUST_URL, headers={"User-Agent": "kiwi-garakuta-build/0.1"})
    with urllib.request.urlopen(request, timeout=45) as response:
        data = response.read()
    actual = hashlib.sha256(data).hexdigest()
    if actual != DUST_SHA256:
        raise SystemExit(f"dust SHA-256 mismatch: {actual}")

    with tempfile.TemporaryDirectory(prefix="kiwi-disk-") as temp:
        temp_path = Path(temp)
        prefix = f"dust-v{DUST_VERSION}-x86_64-pc-windows-gnu/"
        with zipfile.ZipFile(io.BytesIO(data)) as source:
            for name in ("dust.exe", "LICENSE", "README.md"):
                (temp_path / name).write_bytes(source.read(prefix + name))
        subprocess.run([sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean",
                        "--onefile", "--noconsole", "--paths", str(ROOT.parents[0] / "common"),
            "--add-data", f"{ROOT / 'advanced-spec.json'}{os.pathsep}.",
            "--add-data", f"{ROOT / 'upstream-help.txt'}{os.pathsep}.", "--name", "KiwiDisk",
                        "--distpath", str(temp_path / "dist"),
                        "--workpath", str(temp_path / "build"),
                        "--specpath", str(temp_path),
                        "--add-binary", f"{temp_path / 'dust.exe'}{os.pathsep}.",
                        str(ROOT / "main.py")], check=True)
        release = ROOT / "release"
        if release.resolve().parent != ROOT.resolve() or release.is_symlink():
            raise ValueError("Release path is outside the app directory")
        if release.exists():
            shutil.rmtree(release)
        release.mkdir()
        shutil.copy2(temp_path / "dist" / "KiwiDisk.exe", release / "KiwiDisk.exe")
        shutil.copy2(temp_path / "LICENSE", release / "dust-LICENSE")
        shutil.copy2(temp_path / "README.md", release / "dust-README.md")
        shutil.copy2(ROOT / "README.txt", release / "README.txt")
        shutil.copy2(ROOT.parents[1] / "LICENSE", release / "LICENSE")

    output = ROOT / f"KiwiDisk-{VERSION}-win11-x64.zip"
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for file in sorted(release.iterdir()):
            archive.write(file, file.name)
    print(f"Built {output} ({output.stat().st_size:,} bytes)")
    print(f"SHA-256: {hashlib.sha256(output.read_bytes()).hexdigest()}")


if __name__ == "__main__":
    main()
