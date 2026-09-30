"""Build a portable Windows ZIP from a pinned official fd release."""

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
FD_VERSION = "10.5.0"
FD_SHA256 = "a227701b8551c35a9931d9f6da75503cf86d88e182d71fb849a70864c5d57cd7"
FD_URL = (f"https://github.com/sharkdp/fd/releases/download/v{FD_VERSION}/"
          f"fd-v{FD_VERSION}-x86_64-pc-windows-msvc.zip")


def main() -> None:
    if os.name != "nt":
        raise SystemExit("Build this release on Windows.")
    request = urllib.request.Request(FD_URL, headers={"User-Agent": "kiwi-garakuta-build/0.1"})
    with urllib.request.urlopen(request, timeout=45) as response:
        archive_bytes = response.read()
    actual = hashlib.sha256(archive_bytes).hexdigest()
    if actual != FD_SHA256:
        raise SystemExit(f"fd SHA-256 mismatch: {actual}")

    with tempfile.TemporaryDirectory(prefix="kiwi-find-") as temp:
        temp_path = Path(temp)
        prefix = f"fd-v{FD_VERSION}-x86_64-pc-windows-msvc/"
        with zipfile.ZipFile(io.BytesIO(archive_bytes)) as source:
            for name in ("fd.exe", "LICENSE-MIT", "LICENSE-APACHE"):
                (temp_path / name).write_bytes(source.read(prefix + name))
        subprocess.run([sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean",
                        "--onefile", "--noconsole", "--name", "KiwiFind",
                        "--distpath", str(temp_path / "dist"),
                        "--workpath", str(temp_path / "build"),
                        "--specpath", str(temp_path),
                        "--add-binary", f"{temp_path / 'fd.exe'}{os.pathsep}.",
                        str(ROOT / "main.py")], check=True)
        release = ROOT / "release"
        if release.resolve().parent != ROOT.resolve() or release.is_symlink():
            raise ValueError("Release path is outside the app directory")
        if release.exists():
            shutil.rmtree(release)
        release.mkdir()
        shutil.copy2(temp_path / "dist" / "KiwiFind.exe", release / "KiwiFind.exe")
        for name in ("LICENSE-MIT", "LICENSE-APACHE"):
            shutil.copy2(temp_path / name, release / ("fd-" + name))
        shutil.copy2(ROOT / "README.txt", release / "README.txt")
        shutil.copy2(ROOT.parents[1] / "LICENSE", release / "LICENSE")

    output = ROOT / f"KiwiFind-{VERSION}-win11-x64.zip"
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for file in sorted(release.iterdir()):
            archive.write(file, file.name)
    print(f"Built {output} ({output.stat().st_size:,} bytes)")
    print(f"SHA-256: {hashlib.sha256(output.read_bytes()).hexdigest()}")


if __name__ == "__main__":
    main()
