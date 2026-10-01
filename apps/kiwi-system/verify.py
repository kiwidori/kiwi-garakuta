"""Exercise real fastfetch collection and capture a privacy-safe GUI screenshot."""

from __future__ import annotations

import ctypes
import importlib.util
import json
import os
import tempfile
import time
from pathlib import Path

from PIL import ImageGrab

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
SCREENSHOT = ROOT / "site" / "assets" / "screenshots" / "kiwi-system-public.png"
DEMO_ROOT = Path("C:/Users/Public/Documents")


def main() -> None:
    if os.name != "nt" or not DEMO_ROOT.is_dir():
        raise SystemExit("Windows and Public Documents are needed for this check.")
    executable = ROOT / ".tools" / "fastfetch" / "fastfetch.exe"
    if not executable.is_file():
        raise SystemExit("Place verified official fastfetch.exe in .tools/fastfetch first.")
    spec = importlib.util.spec_from_file_location("kiwi_system", HERE / "main.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    actual = module.collect(executable, module.threading.Event())
    assert any(key == "OS" for key, _ in actual), actual
    assert any(key == "CPU" for key, _ in actual), actual
    assert all("user" not in key.lower() and "host" not in key.lower() for key, _ in actual)

    with tempfile.TemporaryDirectory(prefix="KiwiDemo-", dir=DEMO_ROOT) as temp:
        sample = Path(temp) / "sample.json"
        sample.write_text(json.dumps([
            {"type": "OS", "result": {"prettyName": "Windows 11 Pro", "userName": "SECRET_USERNAME"}},
            {"type": "CPU", "result": {"cpu": "AMD Ryzen 7", "cores": {"physical": 8, "logical": 16}}},
            {"type": "GPU", "result": [{"name": "Radeon Graphics", "serial": "SECRET_SERIAL"}]},
            {"type": "Memory", "result": {"total": 32 * 1024 ** 3, "used": 12 * 1024 ** 3}},
            {"type": "Disk", "result": [{"mountpoint": "C:\\", "name": "SECRET_VOLUME", "bytes": {"total": 1024 ** 4, "available": 512 * 1024 ** 3}}]},
            {"type": "Display", "result": [{"name": "SECRET_MONITOR", "output": {"width": 1920, "height": 1080, "refreshRate": 60}}]},
            {"type": "Title", "result": "SECRET_HOST"},
        ], ensure_ascii=False), encoding="utf-8")
        demo = module.summarize(json.loads(sample.read_text(encoding="utf-8")))
        shown = "\n".join(f"{key}: {value}" for key, value in demo)
        assert "SECRET" not in shown and "C:" in shown, shown
        module.resource_dir = lambda: executable.parent
        app = module.App()
        try:
            app.start()
            deadline = time.monotonic() + 20
            while app.running and time.monotonic() < deadline:
                app.update()
                time.sleep(0.05)
            app.update()
            assert not app.running and app.status.get() == "取得完了。", app.status.get()
            assert any(key == "OS" for key, _ in app.rows)
            app.show_rows(demo, "サンプル表示（デモデータ）")
            app.geometry("780x600+120+100")
            app.attributes("-topmost", True)
            app.update()
            app.lift()
            app.focus_force()
            ctypes.windll.user32.SetForegroundWindow(app.winfo_id())
            app.update()
            time.sleep(0.5)
            x, y = app.winfo_rootx(), app.winfo_rooty()
            width, height = app.winfo_width(), app.winfo_height()
            SCREENSHOT.parent.mkdir(parents=True, exist_ok=True)
            ImageGrab.grab(bbox=(x, y, x + width, y + height)).save(SCREENSHOT)
            print(f"PASS: real fastfetch collection, privacy allowlist, GUI; screenshot: {SCREENSHOT}")
        finally:
            app.close()


if __name__ == "__main__":
    main()
