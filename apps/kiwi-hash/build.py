"""Build a portable Windows GUI ZIP from a pinned official b3sum release."""

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
B3SUM_VERSION = "1.8.7"
B3SUM_SHA256 = "fce0c2406a1e92b49fedd02a48a67dc5ba71c3a85eb80a2f950ed985f90e76e2"
B3SUM_URL = (f"https://github.com/BLAKE3-team/BLAKE3/releases/download/{B3SUM_VERSION}/"
                f"b3sum_windows_x64_bin.exe")


def main() -> None:
    if os.name != "nt":
        raise SystemExit("Build this release on Windows.")
    request = urllib.request.Request(B3SUM_URL, headers={"User-Agent": "kiwi-garakuta-build/0.1"})
    with urllib.request.urlopen(request, timeout=45) as response:
        data = response.read()
    digest = hashlib.sha256(data).hexdigest()
    if digest != B3SUM_SHA256:
        raise SystemExit(f"b3sum SHA-256 mismatch: {digest}")

    with tempfile.TemporaryDirectory(prefix="kiwi-hash-") as temp:
        temp_path = Path(temp)
        (temp_path / "b3sum.exe").write_bytes(data)
        hashes = {
            "LICENSE_A2": "00fcc7a934ddbc9ece2a7cc063ac788e284b703b1d705ccbba72d462aa97921e",
            "LICENSE_A2LLVM": "a5695f57ea0c221e0e8b7d784ff774c35e88c3d3270353646a925880bb3492cc",
            "LICENSE_CC0": "a2010f343487d3f7618affe54f789f5487602331c0a8d03f49e9a7c547cf0499",
        }
        for name, expected in hashes.items():
            url = f"https://raw.githubusercontent.com/BLAKE3-team/BLAKE3/{B3SUM_VERSION}/{name}"
            with urllib.request.urlopen(url, timeout=30) as response:
                license_data = response.read()
            if hashlib.sha256(license_data).hexdigest() != expected:
                raise SystemExit(f"{name} hash mismatch")
            (temp_path / name).write_bytes(license_data)
        subprocess.run([
            sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--onefile",
            "--noconsole", "--paths", str(ROOT.parents[0] / "common"),
            "--add-data", f"{ROOT / 'advanced-spec.json'}{os.pathsep}.",
            "--add-data", f"{ROOT / 'upstream-help.txt'}{os.pathsep}.", "--name", "KiwiHash", "--distpath", str(temp_path / "dist"),
            "--workpath", str(temp_path / "build"), "--specpath", str(temp_path),
            "--add-binary", f"{temp_path / 'b3sum.exe'}{os.pathsep}.", str(ROOT / "main.py"),
        ], check=True)
        release = ROOT / "release"
        if release.resolve().parent != ROOT.resolve() or release.is_symlink():
            raise ValueError("Release path is outside the app directory")
        if release.exists():
            shutil.rmtree(release)
        release.mkdir()
        shutil.copy2(temp_path / "dist" / "KiwiHash.exe", release / "KiwiHash.exe")
        for name in hashes:
            shutil.copy2(temp_path / name, release / f"b3sum-{name}")
        shutil.copy2(ROOT / "README.txt", release / "README.txt")
        shutil.copy2(ROOT.parents[1] / "LICENSE", release / "LICENSE")

    output = ROOT / f"KiwiHash-{VERSION}-win11-x64.zip"
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for file in sorted(release.iterdir()):
            archive.write(file, file.name)
    print(f"Built {output} ({output.stat().st_size:,} bytes)")
    print(f"SHA-256: {hashlib.sha256(output.read_bytes()).hexdigest()}")


if __name__ == "__main__":
    main()
