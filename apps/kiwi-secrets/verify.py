"""Exercise real redacted Gitleaks scans and capture a safe Windows GUI screen."""

from __future__ import annotations

import ctypes
import importlib.util
import json
import os
import random
import string
import tempfile
import threading
import time
from pathlib import Path

from PIL import ImageGrab

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
SCREENSHOT = ROOT / "site" / "assets" / "screenshots" / "kiwi-secrets-public.png"
DEMO_ROOT = Path("C:/Users/Public/Documents")


def wait_for_finish(app) -> None:
    deadline = time.monotonic() + 15
    while app.running and time.monotonic() < deadline:
        app.update()
        time.sleep(0.05)
    app.update()
    assert not app.running, "GUI scan timed out"


def main() -> None:
    if os.name != "nt" or not DEMO_ROOT.is_dir():
        raise SystemExit("Windows and Public Documents are required.")
    exe = ROOT / ".tools" / "gitleaks.exe"
    spec = importlib.util.spec_from_file_location("kiwi_secrets", HERE / "main.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    with tempfile.TemporaryDirectory(prefix="KiwiDemo-", dir=DEMO_ROOT) as temp:
        base = Path(temp)
        clean_folder = base / "安全なサンプル"
        clean_folder.mkdir()
        (clean_folder / "メモ.txt").write_text("この文書はサンプルです。", encoding="utf-8")
        assert module.scan(exe, clean_folder, threading.Event()) == []
        folder = base / "公開前チェック"
        folder.mkdir()
        rng = random.Random(2026)
        fake = "gh" + "p_" + "".join(rng.choice(string.ascii_letters + string.digits) for _ in range(36))
        (folder / "設定.env").write_text(f'api_key="{fake}"\n', encoding="utf-8")
        nested = folder / "資料"
        nested.mkdir()
        another = "gh" + "p_" + "".join(rng.choice(string.ascii_letters + string.digits) for _ in range(36))
        (nested / "連携.env").write_text(f'github_token="{another}"\n', encoding="utf-8")
        original = (folder / "設定.env").read_bytes()
        findings = module.scan(exe, folder, threading.Event())
        assert (folder / "設定.env").read_bytes() == original, "Input file was changed"
        assert any(item["rule"] == "github-pat" and item["line"] == 1 for item in findings), "Fake token was not detected"
        assert len(findings) >= 2, "Nested input was not scanned"
        assert fake not in repr(findings) and another not in repr(findings), "A secret was retained"
        assert all(set(item) == {"file", "line", "rule", "path"} for item in findings)
        poisoned = json.dumps([
            {"File": str(folder / "設定.env"), "StartLine": 1, "RuleID": "github-pat", "Secret": fake, "Match": fake},
            {"File": str(base / "outside.env"), "StartLine": 1, "RuleID": "generic-api-key"},
        ]).encode("utf-8")
        filtered = module.parse_report(poisoned, folder)
        assert len(filtered) == 1 and fake not in repr(filtered), "Unsafe report field or path retained"
        try:
            module.scan(exe, base / "missing", threading.Event())
        except ValueError:
            pass
        else:
            raise AssertionError("Missing folder was accepted")
        module.resource_dir = lambda: exe.parent
        app = module.App()
        try:
            app.folder.set(str(folder))
            app.start_scan()
            wait_for_finish(app)
            assert app.findings, app.status.get()
            assert fake not in repr(app.tree.item(app.tree.get_children()[0])), "Secret rendered"
            app.geometry("980x620+120+100")
            app.attributes("-topmost", True)
            app.update()
            app.lift()
            app.focus_force()
            ctypes.windll.user32.SetForegroundWindow(app.winfo_id())
            app.update()
            time.sleep(0.5)
            x, y = app.winfo_rootx(), app.winfo_rooty()
            SCREENSHOT.parent.mkdir(parents=True, exist_ok=True)
            ImageGrab.grab(bbox=(x, y, x + app.winfo_width(), y + app.winfo_height())).save(SCREENSHOT)

            original_scan = module.scan
            def slow_scan(_exe, _folder, cancel):
                if not cancel.wait(5):
                    raise AssertionError("Stop did not signal cancellation")
                raise InterruptedError("チェックを停止しました。")
            module.scan = slow_scan
            app.start_scan()
            app.update()
            app.stop_scan()
            wait_for_finish(app)
            assert "停止" in app.status.get(), app.status.get()
            module.scan = original_scan
            print(f"PASS: clean and synthetic secret scans, redaction, Unicode, path containment, GUI stop; screenshot: {SCREENSHOT}")
        finally:
            app.close()


if __name__ == "__main__":
    main()
