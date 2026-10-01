"""Kiwi Secrets: a read-only GUI for redacted Gitleaks directory scans."""

import os
import sys
import json
import time
import queue
import shutil
import tempfile
import threading
import subprocess
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from pathlib import Path

APP_TITLE = "きうい秘密チェック"
MAX_STDOUT_BYTES = 4 * 1024 * 1024
MAX_STDERR_BYTES = 1 * 1024 * 1024
MAX_DISPLAY_FINDINGS = 1000
SCAN_TIMEOUT_SECONDS = 120
POLL_INTERVAL_MS = 100


def resource_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS)
    return Path(__file__).resolve().parent


def _sanitize_relative_path(raw: str, folder: Path) -> Path | None:
    try:
        raw = raw.replace("\\", "/")
        p = Path(raw)
        if p.is_absolute():
            resolved = p.resolve()
        else:
            resolved = (folder / p).resolve()
        base = folder.resolve()
        if not resolved.is_relative_to(base):
            return None
        rel = resolved.relative_to(base)
        if not rel.parts:
            return None
        return rel
    except Exception:
        return None


def parse_report(data: bytes, folder: Path) -> list[dict]:
    if len(data) > MAX_STDOUT_BYTES:
        raise ValueError("結果が4 MiBを超えました。対象フォルダーを絞ってください。")
    try:
        text = data.decode("utf-8-sig")
        obj = json.loads(text)
    except Exception:
        raise ValueError("チェック結果を読み取れませんでした。") from None
    if not isinstance(obj, list):
        raise ValueError("チェック結果の形式が予期しないものです。")
    results = []
    for item in obj:
        if not isinstance(item, dict):
            continue
        raw_file = item.get("File")
        raw_line = item.get("StartLine")
        raw_rule = item.get("RuleID")
        if not isinstance(raw_file, str) or not raw_file:
            continue
        if not isinstance(raw_rule, str) or not raw_rule:
            continue
        if not isinstance(raw_line, int) or isinstance(raw_line, bool) or raw_line <= 0:
            continue
        rel = _sanitize_relative_path(raw_file, folder)
        if rel is None:
            continue
        results.append({
            "file": str(rel),
            "line": raw_line,
            "rule": "".join(c for c in raw_rule if c.isprintable())[:100],
            "path": folder.resolve() / rel,
        })
    return results


def scan(exe: Path, folder: Path, cancel: threading.Event) -> list[dict]:
    folder = folder.resolve()
    if not folder.is_dir():
        raise ValueError("チェックするフォルダーを選んでください。")
    if not exe.is_file():
        raise ValueError("同梱のgitleaks.exeが見つかりません。")
    if cancel.is_set():
        raise InterruptedError("チェックを停止しました。")

    tmpdir = Path(tempfile.mkdtemp(prefix="kiwi_scan_"))
    try:
        config_path = tmpdir / "rules.toml"
        config_path.write_text("[extend]\nuseDefault = true\n", encoding="utf-8")
        ignore_path = tmpdir / "gitleaks-ignore"
        stdout_path = tmpdir / "stdout.bin"
        stderr_path = tmpdir / "stderr.bin"

        env = {k: v for k, v in os.environ.items() if not k.upper().startswith("GITLEAKS_")}

        cmd = [
            str(exe.resolve()),
            "dir",
            str(folder),
            "--config", str(config_path),
            "--no-banner",
            "--no-color",
            "--redact=100",
            "--report-format", "json",
            "--report-path", "-",
            "--exit-code", "10",
            "--max-decode-depth", "0",
            "--max-archive-depth", "0",
            "--max-target-megabytes", "5",
            "--timeout", str(SCAN_TIMEOUT_SECONDS),
            "--gitleaks-ignore-path", str(ignore_path),
            "--ignore-gitleaks-allow",
        ]

        with open(stdout_path, "wb") as f_out, open(stderr_path, "wb") as f_err:
            proc = subprocess.Popen(
                cmd,
                stdin=subprocess.DEVNULL,
                stdout=f_out,
                stderr=f_err,
                cwd=str(tmpdir),
                env=env,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )

            start = time.monotonic()
            try:
                while proc.poll() is None:
                    if cancel.is_set():
                        raise InterruptedError("チェックを停止しました。")
                    if time.monotonic() - start > SCAN_TIMEOUT_SECONDS:
                        raise TimeoutError("120秒を超えたため停止しました。対象フォルダーを絞ってください。")
                    if stdout_path.stat().st_size > MAX_STDOUT_BYTES:
                        raise ValueError("結果が4 MiBを超えました。対象フォルダーを絞ってください。")
                    if stderr_path.stat().st_size > MAX_STDERR_BYTES:
                        raise ValueError("ログが大きすぎるため停止しました。")
                    time.sleep(0.05)
            finally:
                if proc.poll() is None:
                    proc.kill()
                proc.wait()

            rc = proc.returncode
            if rc not in (0, 10):
                raise ValueError(f"チェックに失敗しました（終了コード {rc}）。")

            data = stdout_path.read_bytes()
            if len(data) > MAX_STDOUT_BYTES:
                raise ValueError("結果が4 MiBを超えました。対象フォルダーを絞ってください。")
            return parse_report(data, folder)
    finally:
        if tmpdir.resolve().parent == Path(tempfile.gettempdir()).resolve() and tmpdir.name.startswith("kiwi_scan_"):
            shutil.rmtree(tmpdir, ignore_errors=True)


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        root = self
        self.root = root
        self.root.title(APP_TITLE)
        self.root.geometry("980x620")
        self.root.minsize(720, 420)

        self.folder = tk.StringVar(value="")
        self.status = tk.StringVar(value="フォルダを選択してください")
        self.findings: list[dict] = []
        self.running = False
        self._cancel = threading.Event()
        self._q: queue.Queue = queue.Queue()

        top = ttk.Frame(root, padding=8)
        top.pack(fill="x")
        ttk.Label(top, text="対象フォルダ:").pack(side="left")
        ttk.Entry(top, textvariable=self.folder).pack(side="left", fill="x", expand=True, padx=4)
        ttk.Button(top, text="選択", command=self._choose_folder).pack(side="left")

        btns = ttk.Frame(root, padding=(8, 0, 8, 8))
        btns.pack(fill="x")
        self.btn_scan = ttk.Button(btns, text="チェック", command=self.start_scan)
        self.btn_scan.pack(side="left")
        self.btn_stop = ttk.Button(btns, text="停止", command=self.stop_scan, state="disabled")
        self.btn_stop.pack(side="left", padx=4)
        ttk.Label(btns, text="秘密の値は表示しません · 誤検出や見逃しがあります").pack(side="right")

        body = ttk.Frame(root, padding=(8, 0, 8, 4))
        body.pack(fill="both", expand=True)
        cols = ("file", "line", "rule")
        self.tree = ttk.Treeview(body, columns=cols, show="headings", selectmode="browse")
        self.tree.heading("file", text="ファイル (相対パス)")
        self.tree.heading("line", text="行")
        self.tree.heading("rule", text="ルール")
        self.tree.column("file", width=420, anchor="w")
        self.tree.column("line", width=60, anchor="e")
        self.tree.column("rule", width=180, anchor="w")
        self.tree.pack(side="left", fill="both", expand=True)
        self.tree.bind("<Double-1>", self._on_double_click)

        sb = ttk.Scrollbar(body, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")

        ttk.Label(root, textvariable=self.status, anchor="w", padding=(8, 0, 8, 8)).pack(fill="x")

        self.root.protocol("WM_DELETE_WINDOW", self.close)
        self.root.after(POLL_INTERVAL_MS, self._poll_queue)

    def _choose_folder(self):
        d = filedialog.askdirectory(title="スキャン対象フォルダを選択")
        if d:
            self.folder.set(d)
            self.status.set("フォルダを選択しました")

    def start_scan(self):
        if self.running:
            return
        folder_str = self.folder.get().strip()
        if not folder_str:
            messagebox.showwarning(APP_TITLE, "フォルダを選択してください")
            return
        folder = Path(folder_str)
        if not folder.is_dir():
            messagebox.showerror(APP_TITLE, "無効なフォルダです")
            return

        self.running = True
        self._cancel.clear()
        self.findings = []
        self.tree.delete(*self.tree.get_children())
        self.btn_scan.config(state="disabled")
        self.btn_stop.config(state="normal")
        self.status.set("チェック中…")

        exe = resource_dir() / "gitleaks.exe"
        t = threading.Thread(target=self._worker, args=(exe, folder), daemon=True)
        t.start()

    def stop_scan(self):
        if self.running:
            self._cancel.set()
            self.status.set("停止中...")

    def _worker(self, exe: Path, folder: Path):
        try:
            results = scan(exe, folder, self._cancel)
            self._q.put(("done", results))
        except (InterruptedError, TimeoutError, ValueError) as error:
            self._q.put(("error", str(error)))
        except Exception:
            self._q.put(("error", "チェックに失敗しました。ファイルへのアクセス権も確認してください。"))

    def _poll_queue(self):
        try:
            while True:
                kind, payload = self._q.get_nowait()
                if kind == "done":
                    self._finish(payload)
                elif kind == "error":
                    self._finish_error(payload)
        except queue.Empty:
            pass
        self.root.after(POLL_INTERVAL_MS, self._poll_queue)

    def _finish(self, results: list[dict]):
        self.running = False
        self.btn_scan.config(state="normal")
        self.btn_stop.config(state="disabled")
        self.findings = results
        self.tree.delete(*self.tree.get_children())
        for r in results[:MAX_DISPLAY_FINDINGS]:
            self.tree.insert("", "end", values=(r["file"], r["line"], r["rule"]))
        total = len(results)
        if total == 0:
            self.status.set("検出なし（ただし、秘密情報の不在を保証するものではありません）")
        else:
            shown = min(total, MAX_DISPLAY_FINDINGS)
            self.status.set(f"候補: {total} 件（表示: {shown} 件）。該当ファイルを確認してください。")

    def _finish_error(self, msg: str):
        self.running = False
        self.btn_scan.config(state="normal")
        self.btn_stop.config(state="disabled")
        self.status.set(msg)

    def _on_double_click(self, _event):
        sel = self.tree.selection()
        if not sel:
            return
        iid = sel[0]
        idx = self.tree.index(iid)
        if idx >= len(self.findings):
            return
        r = self.findings[idx]
        p: Path = r["path"].resolve()
        base = Path(self.folder.get()).resolve()
        try:
            if not p.is_relative_to(base):
                return
            parent = p.parent
            if parent.is_dir():
                os.startfile(str(parent))
        except Exception:
            pass

    def close(self):
        if self.running:
            self._cancel.set()
        self.root.destroy()


def main():
    App().mainloop()


if __name__ == "__main__":
    main()
