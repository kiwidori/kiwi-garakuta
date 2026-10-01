"""Exercise a real bat preview through the GUI and capture its screen."""

from __future__ import annotations

import ctypes
import importlib.util
import os
import tempfile
import threading
import time
from pathlib import Path

from PIL import ImageGrab

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
SCREENSHOT = ROOT / "site" / "assets" / "screenshots" / "kiwi-code-public.png"
DEMO_ROOT = Path("C:/Users/Public/Documents")


def wait_for_finish(app, seconds: int = 15) -> None:
    deadline = time.monotonic() + seconds
    while app.running and time.monotonic() < deadline:
        app.update()
        time.sleep(0.05)
    app.update()
    assert not app.running, "GUI preview timed out"


def main() -> None:
    if os.name != "nt" or not DEMO_ROOT.is_dir():
        raise SystemExit("Windows and Public Documents are needed for this check.")
    bat = ROOT / ".tools" / "bat.exe"
    if not bat.is_file():
        raise SystemExit("Place verified official bat.exe in .tools first.")
    spec = importlib.util.spec_from_file_location("kiwi_code", HERE / "main.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    with tempfile.TemporaryDirectory(prefix="KiwiDemo-", dir=DEMO_ROOT) as temp:
        base = Path(temp)
        source = base / "サンプル.py"
        lines = [
            '"""日本語のサンプルコード。"""',
            "from dataclasses import dataclass",
            "from pathlib import Path",
            "",
            "@dataclass",
            "class Item:",
            "    name: str",
            "    price: int",
            "",
            "def greet(name: str) -> str:",
            '    return f"こんにちは、{name}!"',
            "",
            "for person in ('きうい', 'みかん'):",
            "    print(greet(person))",
            "",
            "items = [",
            '    Item("青いマグカップ", 1200),',
            '    Item("赤いノート", 600),',
            "]",
            "",
            "def affordable(items: list[Item], limit: int) -> list[Item]:",
            "    return [item for item in items if item.price <= limit]",
            "",
            "for item in affordable(items, 1000):",
            '    print(f"おすすめ: {item.name} ({item.price}円)")',
            "",
            "# ファイルを開く操作はGUIから行えます。",
            "sample = Path('サンプル.py')",
            "print(sample.suffix)",
            "",
        ] + [f"# デモ行 {number}" for number in range(31, 531)]
        source.write_text("\n".join(lines) + "\n", encoding="utf-8")
        raw = module.run_bat(bat, source, 1, "TwoDark", threading.Event())
        runs = list(module.ansi_runs(raw))
        visible = "".join(fragment for fragment, _ in runs)
        assert "こんにちは" in visible and "def greet" in visible, visible[:400]
        assert any(color for _, color in runs), "bat did not provide syntax colors"
        assert "\x1b" not in visible, "ANSI escape remained in text"
        tail = module.run_bat(bat, source, 501, "TwoDark", threading.Event())
        assert "デモ行 501" in tail and "デモ行 10" not in tail
        try:
            module.run_bat(bat, source, 0, "TwoDark", threading.Event())
        except ValueError:
            pass
        else:
            raise AssertionError("Invalid line number was accepted")

        module.resource_dir = lambda: bat.parent
        app = module.App()
        try:
            app.source.set(str(source))
            app.start()
            wait_for_finish(app)
            assert app.status.get().startswith("表示完了"), app.status.get()
            assert "こんにちは" in app.preview.get("1.0", "end")
            app.move(module.PAGE_LINES)
            wait_for_finish(app)
            assert "デモ行 501" in app.preview.get("1.0", "end")
            app.move(-module.PAGE_LINES)
            wait_for_finish(app)
            assert "def greet" in app.preview.get("1.0", "end")

            app.geometry("980x700+120+100")
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
            print(f"PASS: Unicode source, syntax colors, line navigation; screenshot: {SCREENSHOT}")
        finally:
            app.close()


if __name__ == "__main__":
    main()
