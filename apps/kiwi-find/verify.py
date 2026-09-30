"""Exercise a real Unicode file-name search and capture the GUI."""

from __future__ import annotations

import importlib.util
import ctypes
import os
import shutil
import tempfile
import time
from pathlib import Path

from PIL import ImageGrab

HERE = Path(__file__).resolve().parent
SCREENSHOT = HERE.parents[1] / "site" / "assets" / "screenshots" / "kiwi-find-public.png"
DEMO_ROOT = Path("C:/Users/Public/Documents")


def main() -> None:
    if os.name != "nt":
        raise SystemExit("The GUI check requires Windows.")
    fd = HERE.parents[1] / ".tools" / "fd.exe"
    if not fd.is_file():
        raise SystemExit("Download the pinned official fd.exe into .tools first.")
    spec = importlib.util.spec_from_file_location("kiwi_find", HERE / "main.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    if not DEMO_ROOT.is_dir():
        raise SystemExit("Public Documents folder is required for a privacy-safe screenshot.")
    with tempfile.TemporaryDirectory(prefix="KiwiDemo-", dir=DEMO_ROOT) as temp:
        base = Path(temp)
        shutil.copy2(fd, base / "fd.exe")
        sample = base / "サンプル文書"
        sample.mkdir()
        (sample / "コーヒー豆.txt").write_text("memo", encoding="utf-8")
        (sample / "コーヒーカップ.txt").write_text("memo", encoding="utf-8")
        (sample / "買い物.txt").write_text("memo", encoding="utf-8")
        (sample / "コーヒー記録.md").write_text("memo", encoding="utf-8")
        module.resource_dir = lambda: base
        app = module.App()
        try:
            app.folder.set(str(sample))
            app.phrase.set("コーヒー")
            app.extension.set("txt")
            app.start_search()
            deadline = time.monotonic() + 10
            while app.start_button.instate(["disabled"]) and time.monotonic() < deadline:
                app.update()
                time.sleep(0.05)
            app.update()
            assert app.count == 2, f"Expected two files, got {app.count}: {app.status.get()}"
            assert all("コーヒー" in app.tree.item(item, "values")[0] for item in app.tree.get_children())
            app.geometry("950x630+120+100")
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
            print(f"PASS: 2 Unicode file-name results; screenshot: {SCREENSHOT}")
        finally:
            app.close()


if __name__ == "__main__":
    main()
