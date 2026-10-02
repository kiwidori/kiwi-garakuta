"""Build a portable Windows GUI ZIP from a pinned official grex release."""

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
GREX_VERSION = "1.4.6"
GREX_SHA256 = "7691dbb8e46339a15d8362b79b2456f508266cf00a55fe685ed69a6259577485"
GREX_URL = (f"https://github.com/pemistahl/grex/releases/download/v{GREX_VERSION}/"
                f"grex-v{GREX_VERSION}-x86_64-pc-windows-msvc.zip")


def main() -> None:
    if os.name != "nt":
        raise SystemExit("Build this release on Windows.")
    request = urllib.request.Request(GREX_URL, headers={"User-Agent": "kiwi-garakuta-build/0.1"})
    with urllib.request.urlopen(request, timeout=45) as response:
        data = response.read()
    digest = hashlib.sha256(data).hexdigest()
    if digest != GREX_SHA256:
        raise SystemExit(f"grex SHA-256 mismatch: {digest}")

    with tempfile.TemporaryDirectory(prefix="kiwi-regex-") as temp:
        temp_path = Path(temp)
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            for name in ("grex.exe",):
                (temp_path / name).write_bytes(archive.read(name))
        license_url = f"https://raw.githubusercontent.com/pemistahl/grex/v{GREX_VERSION}/LICENSE"
        with urllib.request.urlopen(license_url, timeout=30) as response:
            license_data = response.read()
        if hashlib.sha256(license_data).hexdigest() != "c71d239df91726fc519c6eb72d318ec65820627232b2f796219e87dcf35d0ab4":
            raise SystemExit("grex LICENSE hash mismatch")
        (temp_path / "LICENSE").write_bytes(license_data)
        subprocess.run([
            sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--onefile",
            "--noconsole", "--paths", str(ROOT.parents[0] / "common"),
            "--add-data", f"{ROOT / 'advanced-spec.json'}{os.pathsep}.",
            "--add-data", f"{ROOT / 'upstream-help.txt'}{os.pathsep}.", "--name", "KiwiRegex", "--distpath", str(temp_path / "dist"),
            "--workpath", str(temp_path / "build"), "--specpath", str(temp_path),
            "--add-binary", f"{temp_path / 'grex.exe'}{os.pathsep}.", str(ROOT / "main.py"),
        ], check=True)
        release = ROOT / "release"
        if release.resolve().parent != ROOT.resolve() or release.is_symlink():
            raise ValueError("Release path is outside the app directory")
        if release.exists():
            shutil.rmtree(release)
        release.mkdir()
        shutil.copy2(temp_path / "dist" / "KiwiRegex.exe", release / "KiwiRegex.exe")
        shutil.copy2(temp_path / "LICENSE", release / "grex-LICENSE")
        shutil.copy2(ROOT / "README.txt", release / "README.txt")
        shutil.copy2(ROOT.parents[1] / "LICENSE", release / "LICENSE")

    output = ROOT / f"KiwiRegex-{VERSION}-win11-x64.zip"
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for file in sorted(release.iterdir()):
            archive.write(file, file.name)
    print(f"Built {output} ({output.stat().st_size:,} bytes)")
    print(f"SHA-256: {hashlib.sha256(output.read_bytes()).hexdigest()}")


if __name__ == "__main__":
    main()
