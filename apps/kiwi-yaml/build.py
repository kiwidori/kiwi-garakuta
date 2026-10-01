"""Build a portable Windows GUI ZIP from a pinned official yq release."""

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
YQ_VERSION = "4.54.1"
YQ_SHA256 = "b645f47ebb3a0d2fbab52998550bbd0a1706f23b5ca5f5b48e638c580bb70928"
YQ_URL = (f"https://github.com/mikefarah/yq/releases/download/v{YQ_VERSION}/"
                f"yq_windows_amd64.exe")


def main() -> None:
    if os.name != "nt":
        raise SystemExit("Build this release on Windows.")
    request = urllib.request.Request(YQ_URL, headers={"User-Agent": "kiwi-garakuta-build/0.1"})
    with urllib.request.urlopen(request, timeout=45) as response:
        data = response.read()
    digest = hashlib.sha256(data).hexdigest()
    if digest != YQ_SHA256:
        raise SystemExit(f"yq SHA-256 mismatch: {digest}")

    with tempfile.TemporaryDirectory(prefix="kiwi-yaml-") as temp:
        temp_path = Path(temp)
        (temp_path / "yq.exe").write_bytes(data)
        license_url = f"https://raw.githubusercontent.com/mikefarah/yq/v{YQ_VERSION}/LICENSE"
        with urllib.request.urlopen(license_url, timeout=30) as response:
            license_data = response.read()
        if hashlib.sha256(license_data).hexdigest() != "697db34dabb21562fe84487a2ccd031fbd45382b89c2cbdec8ef31682c486040":
            raise SystemExit("yq LICENSE hash mismatch")
        (temp_path / "LICENSE").write_bytes(license_data)
        subprocess.run([
            sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--onefile",
            "--noconsole", "--name", "KiwiYAML", "--distpath", str(temp_path / "dist"),
            "--workpath", str(temp_path / "build"), "--specpath", str(temp_path),
            "--add-binary", f"{temp_path / 'yq.exe'}{os.pathsep}.", str(ROOT / "main.py"),
        ], check=True)
        release = ROOT / "release"
        if release.resolve().parent != ROOT.resolve() or release.is_symlink():
            raise ValueError("Release path is outside the app directory")
        if release.exists():
            shutil.rmtree(release)
        release.mkdir()
        shutil.copy2(temp_path / "dist" / "KiwiYAML.exe", release / "KiwiYAML.exe")
        shutil.copy2(temp_path / "LICENSE", release / "yq-LICENSE")
        shutil.copy2(ROOT / "README.txt", release / "README.txt")
        shutil.copy2(ROOT.parents[1] / "LICENSE", release / "LICENSE")

    output = ROOT / f"KiwiYAML-{VERSION}-win11-x64.zip"
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for file in sorted(release.iterdir()):
            archive.write(file, file.name)
    print(f"Built {output} ({output.stat().st_size:,} bytes)")
    print(f"SHA-256: {hashlib.sha256(output.read_bytes()).hexdigest()}")


if __name__ == "__main__":
    main()
