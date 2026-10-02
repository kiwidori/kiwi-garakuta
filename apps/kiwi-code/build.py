"""Build a portable Windows GUI ZIP using a pinned official bat release."""

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
BAT_VERSION = "0.26.1"
BAT_SHA256 = "0f729b4b6f5f28d395c641eacc2e9ff68d0096b85aa0eec344aa62425144b69b"
BAT_URL = (f"https://github.com/sharkdp/bat/releases/download/v{BAT_VERSION}/"
           f"bat-v{BAT_VERSION}-x86_64-pc-windows-msvc.zip")


def main() -> None:
    if os.name != "nt":
        raise SystemExit("Build this release on Windows.")
    request = urllib.request.Request(BAT_URL, headers={"User-Agent": "kiwi-garakuta-build/0.1"})
    with urllib.request.urlopen(request, timeout=45) as response:
        data = response.read()
    digest = hashlib.sha256(data).hexdigest()
    if digest != BAT_SHA256:
        raise SystemExit(f"bat SHA-256 mismatch: {digest}")

    with tempfile.TemporaryDirectory(prefix="kiwi-code-") as temp:
        temp_path = Path(temp)
        prefix = f"bat-v{BAT_VERSION}-x86_64-pc-windows-msvc/"
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            for name in ("bat.exe", "LICENSE-APACHE", "LICENSE-MIT", "README.md"):
                (temp_path / name).write_bytes(archive.read(prefix + name))
        subprocess.run([
            sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--onefile",
            "--noconsole", "--paths", str(ROOT.parents[0] / "common"),
            "--add-data", f"{ROOT / 'advanced-spec.json'}{os.pathsep}.",
            "--add-data", f"{ROOT / 'upstream-help.txt'}{os.pathsep}.", "--name", "KiwiCode", "--distpath", str(temp_path / "dist"),
            "--workpath", str(temp_path / "build"), "--specpath", str(temp_path),
            "--add-binary", f"{temp_path / 'bat.exe'}{os.pathsep}.", str(ROOT / "main.py"),
        ], check=True)
        release = ROOT / "release"
        if release.resolve().parent != ROOT.resolve() or release.is_symlink():
            raise ValueError("Release path is outside the app directory")
        if release.exists():
            shutil.rmtree(release)
        release.mkdir()
        shutil.copy2(temp_path / "dist" / "KiwiCode.exe", release / "KiwiCode.exe")
        shutil.copy2(temp_path / "LICENSE-APACHE", release / "bat-LICENSE-APACHE")
        shutil.copy2(temp_path / "LICENSE-MIT", release / "bat-LICENSE-MIT")
        shutil.copy2(temp_path / "README.md", release / "bat-README.md")
        shutil.copy2(ROOT / "README.txt", release / "README.txt")
        shutil.copy2(ROOT.parents[1] / "LICENSE", release / "LICENSE")

    output = ROOT / f"KiwiCode-{VERSION}-win11-x64.zip"
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for file in sorted(release.iterdir()):
            archive.write(file, file.name)
    print(f"Built {output} ({output.stat().st_size:,} bytes)")
    print(f"SHA-256: {hashlib.sha256(output.read_bytes()).hexdigest()}")


if __name__ == "__main__":
    main()
