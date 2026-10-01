"""Kiwi JSON: a small, unofficial Windows GUI for jq."""

from __future__ import annotations
import sys as _advanced_sys
from pathlib import Path as _AdvancedPath
if not getattr(_advanced_sys, "frozen", False):
    _advanced_sys.path.insert(0, str(_AdvancedPath(__file__).resolve().parents[1] / "common"))
from advanced import attach

import os
import queue
import subprocess
import sys
import tempfile
import threading
import time
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

MAX_INPUT_BYTES = 20 * 1024 * 1024
MAX_OUTPUT_BYTES = 2 * 1024 * 1024
PREVIEW_CHARS = 120_000
TIMEOUT_SECONDS = 20


def resource_dir() -> Path:
    return Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))


def run_jq(jq: Path, source: Path, expression: str, cancel: threading.Event) -> str:
    if not source.is_file():
        raise ValueError("JSONファイルを選択してください。")
    if source.stat().st_size > MAX_INPUT_BYTES:
        raise ValueError("20 MiBを超えるファイルは処理できません。")
    if not expression.strip():
        raise ValueError("抽出式を入力してください。")
    if not jq.is_file():
        raise FileNotFoundError("同梱のjq.exeが見つかりません。")
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    with tempfile.TemporaryFile() as stdout, tempfile.TemporaryFile() as stderr:
        process = subprocess.Popen(
            [str(jq), "-M", "--", expression, str(source)],
            stdin=subprocess.DEVNULL,
            stdout=stdout,
            stderr=stderr,
            creationflags=flags,
        )
        started = time.monotonic()
        try:
            while process.poll() is None:
                if cancel.is_set():
                    raise InterruptedError("処理を停止しました。")
                if time.monotonic() - started > TIMEOUT_SECONDS:
                    raise TimeoutError("処理が20秒を超えました。")
                if os.fstat(stdout.fileno()).st_size > MAX_OUTPUT_BYTES:
                    raise ValueError("結果が2 MiBを超えました。絞り込む式にしてください。")
                time.sleep(0.05)
        finally:
            if process.poll() is None:
                process.kill()
            process.wait()
        if os.fstat(stdout.fileno()).st_size > MAX_OUTPUT_BYTES:
            raise ValueError("結果が2 MiBを超えました。絞り込む式にしてください。")
        stderr.seek(0)
        error = stderr.read(4096).decode("utf-8", errors="replace").strip()
        if process.returncode:
            raise ValueError(error or f"jqが終了コード{process.returncode}を返しました。")
        stdout.seek(0)
        return stdout.read().decode("utf-8", errors="replace").replace("\r\n", "\n")


class App(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("きういJSON")
        self.geometry("960x680")
        self.minsize(700, 450)
        self.source = tk.StringVar()
        self.status = tk.StringVar(value="JSONファイルを選択してください。")
        self.cancel = threading.Event()
        self.result: str | None = None
        self.running = False
        self.events: queue.Queue[tuple[str | None, str | None]] = queue.Queue()

        controls = ttk.Frame(self, padding=14)
        controls.pack(fill="x")
        ttk.Label(controls, text="JSONファイル").grid(row=0, column=0, sticky="w")
        ttk.Entry(controls, textvariable=self.source).grid(row=0, column=1, sticky="ew", padx=8)
        ttk.Button(controls, text="選択…", command=self.choose).grid(row=0, column=2)
        ttk.Label(controls, text="jq抽出式").grid(row=1, column=0, sticky="w", pady=12)
        self.expression = ttk.Entry(controls)
        self.expression.insert(0, ".")
        self.expression.grid(row=1, column=1, columnspan=2, sticky="ew", padx=(8, 0))
        controls.columnconfigure(1, weight=1)

        actions = ttk.Frame(self, padding=(14, 0, 14, 10))
        actions.pack(fill="x")
        self.run_button = ttk.Button(actions, text="実行", command=self.start)
        self.run_button.pack(side="left")
        self.stop_button = ttk.Button(actions, text="停止", command=self.stop, state="disabled")
        self.stop_button.pack(side="left", padx=8)
        self.save_button = ttk.Button(actions, text="結果を保存…", command=self.save, state="disabled")
        self.save_button.pack(side="left")
        ttk.Label(actions, text="例: .items[] | {name, price}").pack(side="right")

        body = ttk.Frame(self, padding=(14, 0, 14, 0))
        body.pack(fill="both", expand=True)
        self.preview = tk.Text(body, wrap="none", font=("Consolas", 10), state="disabled")
        ybar = ttk.Scrollbar(body, orient="vertical", command=self.preview.yview)
        xbar = ttk.Scrollbar(body, orient="horizontal", command=self.preview.xview)
        self.preview.configure(yscrollcommand=ybar.set, xscrollcommand=xbar.set)
        self.preview.grid(row=0, column=0, sticky="nsew")
        ybar.grid(row=0, column=1, sticky="ns")
        xbar.grid(row=1, column=0, sticky="ew")
        body.rowconfigure(0, weight=1)
        body.columnconfigure(0, weight=1)
        ttk.Label(self, textvariable=self.status, padding=(14, 8)).pack(fill="x")
        # Additional upstream operations run in a separate structured window.
        self.advanced = attach(self, source_dir=Path(__file__).resolve().parent)

    def choose(self) -> None:
        file = filedialog.askopenfilename(filetypes=[("JSONファイル", "*.json"), ("すべてのファイル", "*.*")])
        if file:
            self.source.set(file)

    def start(self) -> None:
        if self.running:
            return
        source = Path(self.source.get().strip())
        expression = self.expression.get()
        self.result = None
        self.cancel = threading.Event()
        self.running = True
        self.run_button.configure(state="disabled")
        self.stop_button.configure(state="normal")
        self.save_button.configure(state="disabled")
        self.status.set("実行中…")
        worker = threading.Thread(target=self._work, args=(source, expression, self.cancel), daemon=True)
        worker.start()
        self.after(50, self._drain)

    def _work(self, source: Path, expression: str, cancel: threading.Event) -> None:
        try:
            result = run_jq(resource_dir() / "jq.exe", source, expression, cancel)
        except Exception as error:
            self.events.put((None, str(error)))
        else:
            self.events.put((result, None))

    def _drain(self) -> None:
        try:
            result, error = self.events.get_nowait()
        except queue.Empty:
            if self.running:
                self.after(50, self._drain)
        else:
            self._finish(result, error)

    def _finish(self, result: str | None, error: str | None) -> None:
        self.running = False
        self.run_button.configure(state="normal")
        self.stop_button.configure(state="disabled")
        self.preview.configure(state="normal")
        self.preview.delete("1.0", "end")
        if error:
            self.status.set(error)
            self.result = None
        else:
            self.result = result
            shown = result[:PREVIEW_CHARS]
            self.preview.insert("1.0", shown)
            self.save_button.configure(state="normal")
            self.status.set("完了。" + (" 表示は先頭部分のみです。" if len(result) > PREVIEW_CHARS else ""))
        self.preview.configure(state="disabled")

    def stop(self) -> None:
        self.cancel.set()
        self.status.set("停止中…")

    def save(self) -> None:
        if self.result is None:
            return
        target = filedialog.asksaveasfilename(defaultextension=".txt", filetypes=[("テキストファイル", "*.txt"), ("JSONファイル", "*.json"), ("すべてのファイル", "*.*")])
        if not target:
            return
        try:
            Path(target).write_text(self.result, encoding="utf-8")
        except OSError as error:
            messagebox.showerror("保存できませんでした", str(error))
        else:
            self.status.set("結果を保存しました。")


if __name__ == "__main__":
    App().mainloop()
