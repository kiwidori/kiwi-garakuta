"""Build a portable Windows GUI ZIP from a pinned official duf release."""

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
DUF_VERSION = "0.9.1"
DUF_SHA256 = "503934be81f847d9ddb1b739834217480633435ad16515dd199e372c0b2e1afc"
DUF_URL = (f"https://github.com/muesli/duf/releases/download/v{DUF_VERSION}/"
                f"duf_{DUF_VERSION}_windows_x86_64.zip")


def main() -> None:
    if os.name != "nt":
        raise SystemExit("Build this release on Windows.")
    request = urllib.request.Request(DUF_URL, headers={"User-Agent": "kiwi-garakuta-build/0.1"})
    with urllib.request.urlopen(request, timeout=45) as response:
        data = response.read()
    digest = hashlib.sha256(data).hexdigest()
    if digest != DUF_SHA256:
        raise SystemExit(f"duf SHA-256 mismatch: {digest}")

    with tempfile.TemporaryDirectory(prefix="kiwi-space-") as temp:
        temp_path = Path(temp)
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            for name in ("duf.exe",):
                (temp_path / name).write_bytes(archive.read(name))
        subprocess.run([
            sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--onefile",
            "--noconsole", "--paths", str(ROOT.parents[0] / "common"),
            "--add-data", f"{ROOT / 'advanced-spec.json'}{os.pathsep}.",
            "--add-data", f"{ROOT / 'upstream-help.txt'}{os.pathsep}.", "--name", "KiwiSpace", "--distpath", str(temp_path / "dist"),
            "--workpath", str(temp_path / "build"), "--specpath", str(temp_path),
            "--add-binary", f"{temp_path / 'duf.exe'}{os.pathsep}.", str(ROOT / "main.py"),
        ], check=True)
        release = ROOT / "release"
        if release.resolve().parent != ROOT.resolve() or release.is_symlink():
            raise ValueError("Release path is outside the app directory")
        if release.exists():
            shutil.rmtree(release)
        release.mkdir()
        shutil.copy2(temp_path / "dist" / "KiwiSpace.exe", release / "KiwiSpace.exe")
        for name in ('duf-LICENSE','duf-README.md','THIRD-PARTY-NOTICES.txt'):
            shutil.copy2(ROOT/name, release/name)
        runtime_notices=[]
        for title,path in [('Python',Path(sys.base_prefix)/'LICENSE.txt'),('Tk',Path(sys.base_prefix)/'tcl'/'tk8.6'/'license.terms')]:
            if not path.is_file():
                raise ValueError(f'{title} runtime license document missing')
            runtime_notices.append(f'=== {title} runtime ===\n'+path.read_text(encoding='utf-8'))
        (release/'Runtime-LICENSES.txt').write_text('\n\n'.join(runtime_notices),encoding='utf-8')
        shutil.copy2(ROOT / "README.txt", release / "README.txt")
        shutil.copy2(ROOT.parents[1] / "LICENSE", release / "LICENSE")

    output = ROOT / f"KiwiSpace-{VERSION}-win11-x64.zip"
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for file in sorted(release.iterdir()):
            archive.write(file, file.name)
    print(f"Built {output} ({output.stat().st_size:,} bytes)")
    print(f"SHA-256: {hashlib.sha256(output.read_bytes()).hexdigest()}")


if __name__ == "__main__":
    main()
