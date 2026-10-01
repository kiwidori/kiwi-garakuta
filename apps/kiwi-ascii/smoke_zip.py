"""Check extracted ZIP contents and GUI launch on Windows."""

from __future__ import annotations

import argparse
import ctypes
import os
import subprocess
import tempfile
import time
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ZIP = HERE / "KiwiASCII-0.1.0-win11-x64.zip"


def find_window(title: str) -> int:
    matches: list[int] = []
    callback_type = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)

    def visitor(hwnd: int, _: int) -> bool:
        length = ctypes.windll.user32.GetWindowTextLengthW(hwnd)
        if length:
            buffer = ctypes.create_unicode_buffer(length + 1)
            ctypes.windll.user32.GetWindowTextW(hwnd, buffer, length + 1)
            if buffer.value == title:
                matches.append(hwnd)
        return True

    ctypes.windll.user32.EnumWindows(callback_type(visitor), 0)
    return matches[0] if matches else 0


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--zip", type=Path, default=ZIP)
    args = parser.parse_args()
    if os.name != "nt":
        raise SystemExit("ZIP smoke test requires Windows.")
    with zipfile.ZipFile(args.zip) as archive:
        expected = {"KiwiASCII.exe", "README.txt", "LICENSE", "ascii-image-converter-LICENSE.txt", "ascii-image-converter-README.md", "THIRD-PARTY-NOTICES.txt", "Pillow-LICENSE.txt", "Runtime-LICENSES.txt"}
        assert expected <= set(archive.namelist()), "ZIP is missing required files"
        with tempfile.TemporaryDirectory(prefix="kiwi-zip-check-") as temp:
            archive.extractall(temp)
            process = subprocess.Popen([str(Path(temp) / "KiwiASCII.exe")])
            try:
                deadline = time.monotonic() + 15
                window = 0
                while time.monotonic() < deadline and not window:
                    window = find_window("きうい文字絵")
                    if not window:
                        time.sleep(0.2)
                assert window, f"GUI did not open (exit={process.poll()})"
                ctypes.windll.user32.PostMessageW(window, 0x0010, 0, 0)
                process.wait(timeout=10)
                print("PASS: extracted ZIP, licenses present, GUI opened and closed")
            finally:
                if process.poll() is None:
                    subprocess.run(["taskkill", "/F", "/T", "/PID", str(process.pid)], capture_output=True)
                    process.wait(timeout=10)


if __name__ == "__main__":
    main()
