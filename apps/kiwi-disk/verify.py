"""Exercise a real dust scan through the GUI and capture the result."""

from __future__ import annotations

import importlib.util
import ctypes
import os
import shutil
import sys
import tempfile
import time
from pathlib import Path

from PIL import ImageGrab

HERE = Path(__file__).resolve().parent
SCREENSHOT = HERE.parents[1] / "site" / "assets" / "screenshots" / "kiwi-disk.png"


def main() -> None:
    if os.name != "nt":
        raise SystemExit("The GUI check requires Windows.")
    dust = HERE.parents[1] / ".tools" / "dust.exe"
    if not dust.is_file():
        raise SystemExit("Download the pinned official dust.exe into .tools first.")
    spec = importlib.util.spec_from_file_location("kiwi_disk", HERE / "main.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    with tempfile.TemporaryDirectory(prefix="kiwi-disk-verify-") as temp:
        base = Path(temp)
        shutil.copy2(dust, base / "dust.exe")
        sample = base / "サンプル文書"
        nested = sample / "資料"
        nested.mkdir(parents=True)
        (sample / "大きいファイル.bin").write_bytes(b"a" * 180_000)
        (nested / "小さいメモ.txt").write_bytes(b"b" * 12_000)
        module.resource_dir = lambda: base
        app = module.App()
        try:
            app.folder.set(str(sample))
            app.depth.set("3")
            app.start_scan()
            deadline = time.monotonic() + 20
            while app.start_button.instate(["disabled"]) and time.monotonic() < deadline:
                app.update()
                time.sleep(0.05)
            app.update()
            assert app.status.get().startswith("解析完了"), app.status.get()
            paths = {path.name for path in app.paths.values()}
            assert {"サンプル文書", "大きいファイル.bin", "資料", "小さいメモ.txt"} <= paths, paths
            app.geometry("1000x680+120+100")
            app.attributes("-topmost", True)
            app.update()
            app.lift()
            app.focus_force()
            ctypes.windll.user32.SetForegroundWindow(app.winfo_id())
            app.update()
            time.sleep(0.6)
            x, y = app.winfo_rootx(), app.winfo_rooty()
            width, height = app.winfo_width(), app.winfo_height()
            SCREENSHOT.parent.mkdir(parents=True, exist_ok=True)
            ImageGrab.grab(bbox=(x, y, x + width, y + height)).save(SCREENSHOT)
            module.command = lambda *_: [sys.executable, "-c", "import time; time.sleep(20)"]
            app.start_scan()
            deadline = time.monotonic() + 5
            while app.process is None and time.monotonic() < deadline:
                app.update()
                time.sleep(0.02)
            assert app.process is not None, "Cancellation fixture did not start"
            app.stop_scan()
            deadline = time.monotonic() + 5
            while app.start_button.instate(["disabled"]) and time.monotonic() < deadline:
                app.update()
                time.sleep(0.05)
            assert app.status.get() == "解析を停止しました。", app.status.get()
            print(f"PASS: Unicode disk tree, byte sizes, and cancellation; screenshot: {SCREENSHOT}")
        finally:
            app.close()


if __name__ == "__main__":
    main()
