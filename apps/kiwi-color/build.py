"""Build a portable Windows GUI ZIP from a pinned official pastel release."""

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
VERSION = "0.2.0"
PASTEL_VERSION = "0.12.0"
PASTEL_SHA256 = "51e914b0308b089f032c481e786d67a9f11d8857f4ffe99405f3452e77582393"
PASTEL_URL = (f"https://github.com/sharkdp/pastel/releases/download/v{PASTEL_VERSION}/"
                f"pastel-v{PASTEL_VERSION}-x86_64-pc-windows-msvc.zip")


def main() -> None:
    if os.name != "nt":
        raise SystemExit("Build this release on Windows.")
    request = urllib.request.Request(PASTEL_URL, headers={"User-Agent": "kiwi-garakuta-build/0.1"})
    with urllib.request.urlopen(request, timeout=45) as response:
        data = response.read()
    digest = hashlib.sha256(data).hexdigest()
    if digest != PASTEL_SHA256:
        raise SystemExit(f"pastel SHA-256 mismatch: {digest}")

    with tempfile.TemporaryDirectory(prefix="kiwi-color-") as temp:
        temp_path = Path(temp)
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            for name in ("pastel.exe", "LICENSE-APACHE", "LICENSE-MIT", "README.md"):
                (temp_path / name).write_bytes(archive.read(f"pastel-v{PASTEL_VERSION}-x86_64-pc-windows-msvc/{name}"))
        subprocess.run([
            sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--onefile",
            "--noconsole", "--paths", str(ROOT.parents[0] / "common"),
            "--add-data", f"{ROOT / 'advanced-spec.json'}{os.pathsep}.",
            "--add-data", f"{ROOT / 'upstream-help.txt'}{os.pathsep}.", "--name", "KiwiColor", "--distpath", str(temp_path / "dist"),
            "--workpath", str(temp_path / "build"), "--specpath", str(temp_path),
            "--add-binary", f"{temp_path / 'pastel.exe'}{os.pathsep}.", str(ROOT / "main.py"),
        ], check=True)
        release = ROOT / "release"
        if release.resolve().parent != ROOT.resolve() or release.is_symlink():
            raise ValueError("Release path is outside the app directory")
        if release.exists():
            shutil.rmtree(release)
        release.mkdir()
        shutil.copy2(temp_path / "dist" / "KiwiColor.exe", release / "KiwiColor.exe")
        for name in ("LICENSE-APACHE", "LICENSE-MIT"):
            shutil.copy2(temp_path / name, release / f"pastel-{name}")
        shutil.copy2(temp_path / "README.md", release / "pastel-README.md")
        shutil.copy2(ROOT / "README.txt", release / "README.txt")
        shutil.copy2(ROOT.parents[1] / "LICENSE", release / "LICENSE")

    output = ROOT / f"KiwiColor-{VERSION}-win11-x64.zip"
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for file in sorted(release.iterdir()):
            archive.write(file, file.name)
    print(f"Built {output} ({output.stat().st_size:,} bytes)")
    print(f"SHA-256: {hashlib.sha256(output.read_bytes()).hexdigest()}")


if __name__ == "__main__":
    main()
