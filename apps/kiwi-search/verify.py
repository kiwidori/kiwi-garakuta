"""Exercise a real search through the GUI and capture the resulting screen."""

from __future__ import annotations

import importlib.util
import os
import shutil
import tempfile
import time
from pathlib import Path

from PIL import ImageGrab

HERE = Path(__file__).resolve().parent
SCREENSHOT = HERE.parents[1] / "site" / "assets" / "screenshots" / "kiwi-search.png"


def main() -> None:
    if os.name != "nt":
        raise SystemExit("The GUI check requires Windows.")
    rg = shutil.which("rg")
    if not rg:
        raise SystemExit("Install ripgrep before running the local check.")
    spec = importlib.util.spec_from_file_location("kiwi_search", HERE / "main.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    with tempfile.TemporaryDirectory(prefix="kiwi-verify-") as temp:
        base = Path(temp)
        shutil.copy2(rg, base / "rg.exe")
        sample = base / "サンプル文書"
        sample.mkdir()
        (sample / "買い物メモ.txt").write_text("コーヒー豆を買う\n砂糖を買う\n", encoding="utf-8")
        (sample / "仕事メモ.txt").write_text("資料を確認する\nコーヒー休憩\n", encoding="utf-8")
        module.resource_dir = lambda: base
        app = module.App()
        try:
            app.folder.set(str(sample))
            app.phrase.set("コーヒー")
            app.start_search()
            deadline = time.monotonic() + 10
            while app.start_button.instate(["disabled"]) and time.monotonic() < deadline:
                app.update()
                time.sleep(0.05)
            app.update()
            assert app.count == 2, f"Expected two matches, got {app.count}: {app.status.get()}"
            assert len(app.tree.get_children()) == 2
            assert all("コーヒー" in app.tree.item(item, "values")[2] for item in app.tree.get_children())
            app.geometry("950x650+120+100")
            app.update()
            app.lift()
            app.focus_force()
            app.update()
            time.sleep(0.3)
            x, y = app.winfo_rootx(), app.winfo_rooty()
            width, height = app.winfo_width(), app.winfo_height()
            SCREENSHOT.parent.mkdir(parents=True, exist_ok=True)
            ImageGrab.grab(bbox=(x, y, x + width, y + height)).save(SCREENSHOT)
            print(f"PASS: 2 Unicode search results; screenshot: {SCREENSHOT}")
        finally:
            app.close()


if __name__ == "__main__":
    main()
