"""Check jq through the GUI on Windows and capture a privacy-safe screenshot."""

from __future__ import annotations

import ctypes
import importlib.util
import json
import os
import tempfile
import threading
import time
from pathlib import Path

from PIL import ImageGrab

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
SCREENSHOT = ROOT / "site" / "assets" / "screenshots" / "kiwi-json-public.png"
DEMO_ROOT = Path("C:/Users/Public/Documents")


def main() -> None:
    if os.name != "nt" or not DEMO_ROOT.is_dir():
        raise SystemExit("Windows and Public Documents are needed for this check.")
    jq = ROOT / ".tools" / "jq.exe"
    if not jq.is_file():
        raise SystemExit("Place verified official jq.exe in .tools first.")
    spec = importlib.util.spec_from_file_location("kiwi_json", HERE / "main.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    with tempfile.TemporaryDirectory(prefix="KiwiDemo-", dir=DEMO_ROOT) as temp:
        base = Path(temp)
        source = base / "商品一覧.json"
        source.write_text(json.dumps({"items": [
            {"name": "青いマグカップ", "price": 1200},
            {"name": "赤いノート", "price": 600},
        ]}, ensure_ascii=False), encoding="utf-8")
        direct = module.run_jq(jq, source, '.items[] | select(.price >= 1000) | {name, price}', threading.Event())
        assert "青いマグカップ" in direct and "赤いノート" not in direct, direct
        try:
            module.run_jq(jq, source, '.items[', threading.Event())
        except ValueError as error:
            assert "syntax error" in str(error), str(error)
        else:
            raise AssertionError("Invalid filter was accepted")

        module.resource_dir = lambda: jq.parent
        app = module.App()
        try:
            app.source.set(str(source))
            app.expression.delete(0, "end")
            app.expression.insert(0, '.items[] | {name, price}')
            app.start()
            deadline = time.monotonic() + 15
            while app.running and time.monotonic() < deadline:
                app.update()
                time.sleep(0.05)
            app.update()
            assert not app.running, "GUI execution timed out"
            assert app.result is not None and "青いマグカップ" in app.result, app.status.get()
            assert "赤いノート" in app.result
            destination = base / "結果.json"
            module.filedialog.asksaveasfilename = lambda **_: str(destination)
            app.save()
            assert destination.read_text(encoding="utf-8") == app.result

            app.geometry("960x680+120+100")
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
            print(f"PASS: Unicode JSON, filters, errors, GUI save; screenshot: {SCREENSHOT}")
        finally:
            app.destroy()


if __name__ == "__main__":
    main()
