"""Build the three Go-based wrappers from hash-pinned official Windows assets."""
from __future__ import annotations
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import urllib.request
import zipfile


def fetch(url, sha):
    request = urllib.request.Request(url, headers={'User-Agent': 'kiwi-garakuta-build/0.1'})
    with urllib.request.urlopen(request, timeout=90) as response:
        data = response.read()
    if hashlib.sha256(data).hexdigest() != sha:
        raise ValueError('Official asset SHA-256 mismatch')
    return data


def build(root):
    root = Path(root).resolve()
    if os.name != 'nt':
        raise SystemExit('Build on Windows.')
    import tkinter
    if tkinter.Tcl().call('info','patchlevel') != '8.6.15':
        raise ValueError('Update the pinned Tcl runtime license for this Python installation before building.')
    tcl_license=root.parent/'common'/'tcl-8.6.15-LICENSE.terms'
    if hashlib.sha256(tcl_license.read_bytes()).hexdigest() != 'c0a69a2bfd757361ec7e6143973b103c90409316b49e9c88db26ad6388e79f16':
        raise ValueError('Tcl runtime license SHA-256 mismatch')
    pin = json.loads((root / 'upstream-pin.json').read_text(encoding='utf-8'))
    data = fetch(pin['url'], pin['sha'])
    license_data = fetch(pin['license_url'], pin['license_sha'])
    with tempfile.TemporaryDirectory(prefix=pin['slug'] + '-') as folder:
        temp = Path(folder)
        binary = zipfile.ZipFile(io.BytesIO(data)).read(pin['exe']) if pin['asset'].endswith('.zip') else data
        (temp / pin['exe']).write_bytes(binary)
        command = [sys.executable, '-m', 'PyInstaller', '--noconfirm', '--clean', '--onefile', '--noconsole',
                   '--paths', str(root.parent / 'common'), '--name', pin['app_exe'],
                   '--distpath', str(temp/'dist'), '--workpath', str(temp/'build'), '--specpath', str(temp),
                   '--add-binary', f"{temp/pin['exe']}{os.pathsep}."]
        for name in ('profile.json', 'advanced-spec.json', 'upstream-help.txt'):
            command += ['--add-data', f'{root/name}{os.pathsep}.']
        subprocess.run([*command, str(root/'main.py')], check=True)
        release = root / 'release'
        if release.is_symlink() or release.resolve().parent != root:
            raise ValueError('Unsafe release directory')
        if release.exists():
            shutil.rmtree(release)
        release.mkdir()
        shutil.copy2(temp/'dist'/f"{pin['app_exe']}.exe", release)
        (release/'UPSTREAM-LICENSE.txt').write_bytes(license_data)
        for name in ('README.txt', 'THIRD-PARTY-NOTICES.txt'):
            shutil.copy2(root/name, release/name)
        shutil.copy2(root.parents[1]/'LICENSE', release/'LICENSE')
        notices = []
        for title, path in [('Python', Path(sys.base_prefix)/'LICENSE.txt'),
                            ('Tcl 8.6.15', root.parent/'common'/'tcl-8.6.15-LICENSE.terms'),
                            ('Tk', Path(sys.base_prefix)/'tcl'/'tk8.6'/'license.terms')]:
            if not path.is_file():
                raise ValueError(f'{title} runtime license missing')
            notices.append(f'=== {title} ===\n' + path.read_text(encoding='utf-8'))
        (release/'Runtime-LICENSES.txt').write_text('\n\n'.join(notices), encoding='utf-8')
    output = root/f"{pin['app_exe']}-{pin['version']}-win11-x64.zip"
    with zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for file in sorted(release.iterdir()):
            archive.write(file, file.name)
    print(f'Built {output.name}: {output.stat().st_size} bytes; SHA-256 {hashlib.sha256(output.read_bytes()).hexdigest()}')
