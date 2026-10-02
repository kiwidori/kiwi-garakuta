"""Build a portable Windows GUI ZIP from a pinned official xh release."""

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
XH_VERSION = "0.26.2"
XH_SHA256 = "7907c1ef225382fb5955c8274aa23e31b70622c4d39dbc76cf945dc8ce15a78d"
XH_URL = (f"https://github.com/ducaale/xh/releases/download/v{XH_VERSION}/"
                f"xh-v{XH_VERSION}-x86_64-pc-windows-msvc.zip")


def main() -> None:
    if os.name != "nt":
        raise SystemExit("Build this release on Windows.")
    request = urllib.request.Request(XH_URL, headers={"User-Agent": "kiwi-garakuta-build/0.1"})
    with urllib.request.urlopen(request, timeout=45) as response:
        data = response.read()
    digest = hashlib.sha256(data).hexdigest()
    if digest != XH_SHA256:
        raise SystemExit(f"xh SHA-256 mismatch: {digest}")

    with tempfile.TemporaryDirectory(prefix="kiwi-http-") as temp:
        temp_path = Path(temp)
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            for name in ("xh.exe", "LICENSE", "README.md"):
                (temp_path / name).write_bytes(archive.read(f"xh-v{XH_VERSION}-x86_64-pc-windows-msvc/{name}"))
        subprocess.run([
            sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--onefile",
            "--noconsole", "--paths", str(ROOT.parents[0] / "common"),
            "--add-data", f"{ROOT / 'advanced-spec.json'}{os.pathsep}.",
            "--add-data", f"{ROOT / 'upstream-help.txt'}{os.pathsep}.", "--name", "KiwiHTTP", "--distpath", str(temp_path / "dist"),
            "--workpath", str(temp_path / "build"), "--specpath", str(temp_path),
            "--add-binary", f"{temp_path / 'xh.exe'}{os.pathsep}.", str(ROOT / "main.py"),
        ], check=True)
        release = ROOT / "release"
        if release.resolve().parent != ROOT.resolve() or release.is_symlink():
            raise ValueError("Release path is outside the app directory")
        if release.exists():
            shutil.rmtree(release)
        release.mkdir()
        shutil.copy2(temp_path / "dist" / "KiwiHTTP.exe", release / "KiwiHTTP.exe")
        shutil.copy2(temp_path / "LICENSE", release / "xh-LICENSE")
        shutil.copy2(temp_path / "README.md", release / "xh-README.md")
        shutil.copy2(ROOT / "README.txt", release / "README.txt")
        shutil.copy2(ROOT.parents[1] / "LICENSE", release / "LICENSE")

    output = ROOT / f"KiwiHTTP-{VERSION}-win11-x64.zip"
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for file in sorted(release.iterdir()):
            archive.write(file, file.name)
    print(f"Built {output} ({output.stat().st_size:,} bytes)")
    print(f"SHA-256: {hashlib.sha256(output.read_bytes()).hexdigest()}")


if __name__ == "__main__":
    main()
