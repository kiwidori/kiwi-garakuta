"""Build a portable Windows release from a pinned official ripgrep binary."""

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
RG_VERSION = "15.2.0"
RG_SHA256 = "71b2fef860abe467217a538ff31de02f5258807c0129f771846f87bd029aafc5"
RG_URL = ("https://github.com/BurntSushi/ripgrep/releases/download/"
          f"{RG_VERSION}/ripgrep-{RG_VERSION}-x86_64-pc-windows-msvc.zip")


def main() -> None:
    if os.name != "nt":
        raise SystemExit("Build this release on Windows.")
    request = urllib.request.Request(RG_URL, headers={"User-Agent": "kiwi-garakuta-build/0.1"})
    with urllib.request.urlopen(request, timeout=45) as response:
        archive_bytes = response.read()
    actual = hashlib.sha256(archive_bytes).hexdigest()
    if actual != RG_SHA256:
        raise SystemExit(f"ripgrep SHA-256 mismatch: {actual}")

    with tempfile.TemporaryDirectory(prefix="kiwi-search-") as temp:
        temp_path = Path(temp)
        prefix = f"ripgrep-{RG_VERSION}-x86_64-pc-windows-msvc/"
        with zipfile.ZipFile(io.BytesIO(archive_bytes)) as source:
            for name in ("rg.exe", "COPYING", "LICENSE-MIT", "UNLICENSE"):
                (temp_path / name).write_bytes(source.read(prefix + name))
        subprocess.run([sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean",
                        "--onefile", "--noconsole", "--name", "KiwiSearch",
                        "--distpath", str(temp_path / "dist"),
                        "--workpath", str(temp_path / "build"),
                        "--specpath", str(temp_path),
                        "--add-binary", f"{temp_path / 'rg.exe'}{os.pathsep}.",
                        str(ROOT / "main.py")], check=True)
        release = ROOT / "release"
        if release.resolve().parent != ROOT.resolve() or release.is_symlink():
            raise ValueError("Release path is outside the app directory")
        if release.exists():
            shutil.rmtree(release)
        release.mkdir()
        shutil.copy2(temp_path / "dist" / "KiwiSearch.exe", release / "KiwiSearch.exe")
        for name in ("COPYING", "LICENSE-MIT", "UNLICENSE"):
            shutil.copy2(temp_path / name, release / ("ripgrep-" + name))
        shutil.copy2(ROOT / "README.txt", release / "README.txt")
        shutil.copy2(ROOT.parents[1] / "LICENSE", release / "LICENSE")

    output = ROOT / f"KiwiSearch-{VERSION}-win11-x64.zip"
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for file in sorted(release.iterdir()):
            archive.write(file, file.name)
    print(f"Built {output} ({output.stat().st_size:,} bytes)")
    print(f"SHA-256: {hashlib.sha256(output.read_bytes()).hexdigest()}")


if __name__ == "__main__":
    main()
