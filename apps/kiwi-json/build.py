"""Build a portable Windows ZIP using pinned, official jq binaries."""

from __future__ import annotations

import hashlib
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
JQ_VERSION = "1.8.2"
JQ_SHA256 = "a6fc67fedaf9128a3309a1e2ebb8b986aeccf70122ee46d2cb4849e423f0c627"
COPYING_SHA256 = "ad2b4a266b2268939c1446979759706077421cf906a203aa188c6f396e8cfd74"
JQ_URL = f"https://github.com/jqlang/jq/releases/download/jq-{JQ_VERSION}/jq-windows-amd64.exe"
COPYING_URL = f"https://raw.githubusercontent.com/jqlang/jq/jq-{JQ_VERSION}/COPYING"


def fetch(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": "kiwi-garakuta-build/0.1"})
    with urllib.request.urlopen(request, timeout=45) as response:
        return response.read()


def main() -> None:
    if os.name != "nt":
        raise SystemExit("Build this release on Windows.")
    binary = fetch(JQ_URL)
    digest = hashlib.sha256(binary).hexdigest()
    if digest != JQ_SHA256:
        raise SystemExit(f"jq SHA-256 mismatch: {digest}")
    copying = fetch(COPYING_URL)
    if hashlib.sha256(copying).hexdigest() != COPYING_SHA256:
        raise SystemExit("jq COPYING SHA-256 mismatch")

    with tempfile.TemporaryDirectory(prefix="kiwi-json-") as temp:
        temp_path = Path(temp)
        (temp_path / "jq.exe").write_bytes(binary)
        subprocess.run([
            sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--onefile",
            "--noconsole", "--paths", str(ROOT.parents[0] / "common"),
            "--add-data", f"{ROOT / 'advanced-spec.json'}{os.pathsep}.",
            "--add-data", f"{ROOT / 'upstream-help.txt'}{os.pathsep}.", "--name", "KiwiJSON", "--distpath", str(temp_path / "dist"),
            "--workpath", str(temp_path / "build"), "--specpath", str(temp_path),
            "--add-binary", f"{temp_path / 'jq.exe'}{os.pathsep}.", str(ROOT / "main.py"),
        ], check=True)
        release = ROOT / "release"
        if release.resolve().parent != ROOT.resolve() or release.is_symlink():
            raise ValueError("Release path is outside the app directory")
        if release.exists():
            shutil.rmtree(release)
        release.mkdir()
        shutil.copy2(temp_path / "dist" / "KiwiJSON.exe", release / "KiwiJSON.exe")
        (release / "jq-COPYING").write_bytes(copying)
        shutil.copy2(ROOT / "README.txt", release / "README.txt")
        shutil.copy2(ROOT.parents[1] / "LICENSE", release / "LICENSE")

    output = ROOT / f"KiwiJSON-{VERSION}-win11-x64.zip"
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for file in sorted(release.iterdir()):
            archive.write(file, file.name)
    print(f"Built {output} ({output.stat().st_size:,} bytes)")
    print(f"SHA-256: {hashlib.sha256(output.read_bytes()).hexdigest()}")


if __name__ == "__main__":
    main()
