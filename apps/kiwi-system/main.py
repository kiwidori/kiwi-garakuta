"""Kiwi System: a privacy-conscious, unofficial GUI for fastfetch."""

from __future__ import annotations

import json
import os
import queue
import re
import subprocess
import sys
import tempfile
import threading
import time
import tkinter as tk
from pathlib import Path
from tkinter import ttk

MAX_OUTPUT_BYTES = 1_000_000
TIMEOUT_SECONDS = 15
MODULES = "OS:CPU:GPU:Memory:Disk:Display"
DRIVE = re.compile(r"^[A-Za-z]:\\$")


def resource_dir() -> Path:
    return Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))


def clean(value: object, limit: int = 120) -> str:
    if not isinstance(value, str):
        return ""
    return "".join(character for character in value if character.isprintable())[:limit].strip()


def size(value: object) -> str:
    if not isinstance(value, (int, float)) or isinstance(value, bool) or value < 0:
        return ""
    gib = value / (1024 ** 3)
    return f"{gib:.1f} GiB"


def summarize(data: object) -> list[tuple[str, str]]:
    """Extract only allowlisted fields from fastfetch's JSON output."""
    if not isinstance(data, list):
        raise ValueError("システム情報の形式が予期しないものです。")
    modules = {entry["type"]: entry.get("result") for entry in data
               if isinstance(entry, dict) and isinstance(entry.get("type"), str)}
    rows: list[tuple[str, str]] = []
    os_data = modules.get("OS")
    if isinstance(os_data, dict):
        os_name = clean(os_data.get("prettyName"))
        if os_name:
            rows.append(("OS", os_name))
    cpu = modules.get("CPU")
    if isinstance(cpu, dict):
        cpu_name = clean(cpu.get("cpu"))
        if cpu_name:
            rows.append(("CPU", cpu_name))
        cores = cpu.get("cores")
        if isinstance(cores, dict):
            physical, logical = cores.get("physical"), cores.get("logical")
            if isinstance(physical, int) and isinstance(logical, int) and 0 < physical <= logical <= 1024:
                rows.append(("CPUコア", f"{physical}コア / {logical}スレッド"))
    gpus = modules.get("GPU")
    if isinstance(gpus, list):
        for index, gpu in enumerate(gpus[:4], 1):
            if isinstance(gpu, dict):
                name = clean(gpu.get("name"))
                if name:
                    rows.append((f"GPU {index}", name))
    memory = modules.get("Memory")
    if isinstance(memory, dict):
        total, used = size(memory.get("total")), size(memory.get("used"))
        if total:
            rows.append(("メモリ", f"{total}（使用中 {used}）" if used else total))
    disks = modules.get("Disk")
    if isinstance(disks, list):
        for disk in disks[:12]:
            if not isinstance(disk, dict):
                continue
            mount = disk.get("mountpoint")
            values = disk.get("bytes")
            if not isinstance(mount, str) or not DRIVE.fullmatch(mount) or not isinstance(values, dict):
                continue
            total, free = size(values.get("total")), size(values.get("available"))
            if total:
                rows.append((f"ドライブ {mount[:2].upper()}", f"合計 {total} / 空き {free}" if free else f"合計 {total}"))
    displays = modules.get("Display")
    if isinstance(displays, list):
        for index, display in enumerate(displays[:6], 1):
            if not isinstance(display, dict) or not isinstance(display.get("output"), dict):
                continue
            output = display["output"]
            width, height = output.get("width"), output.get("height")
            if not (isinstance(width, int) and isinstance(height, int) and 1 <= width <= 20000 and 1 <= height <= 20000):
                continue
            hz = output.get("refreshRate")
            rate = f" / {hz:.0f} Hz" if isinstance(hz, (int, float)) and 1 <= hz <= 1000 else ""
            rows.append((f"画面 {index}", f"{width} × {height}{rate}"))
    if not rows:
        raise ValueError("表示できるシステム情報がありません。")
    return rows


def collect(executable: Path, cancel: threading.Event) -> list[tuple[str, str]]:
    if not executable.is_file():
        raise FileNotFoundError("同梱のfastfetch.exeが見つかりません。")
    command = [str(executable), "--config", "none", "--format", "json", "--structure", MODULES]
    with tempfile.TemporaryFile() as stdout, tempfile.TemporaryFile() as stderr:
        process = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=stdout, stderr=stderr,
                                   creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        started = time.monotonic()
        try:
            while process.poll() is None:
                if cancel.is_set():
                    raise InterruptedError("取得を停止しました。")
                if time.monotonic() - started > TIMEOUT_SECONDS:
                    raise TimeoutError("取得が15秒を超えました。")
                if os.fstat(stdout.fileno()).st_size > MAX_OUTPUT_BYTES:
                    raise ValueError("システム情報が大きすぎます。")
                time.sleep(0.05)
        finally:
            if process.poll() is None:
                process.kill()
            process.wait()
        if os.fstat(stdout.fileno()).st_size > MAX_OUTPUT_BYTES:
            raise ValueError("システム情報が大きすぎます。")
        stderr.seek(0)
        error = stderr.read(2048).decode("utf-8", errors="replace").strip()
        if process.returncode:
            raise ValueError(error or f"fastfetchが終了コード{process.returncode}を返しました。")
        stdout.seek(0)
        try:
            return summarize(json.loads(stdout.read().decode("utf-8-sig")))
        except (UnicodeError, json.JSONDecodeError) as error:
            raise ValueError("システム情報を読み取れませんでした。") from error


class App(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("きういPC情報")
        self.geometry("780x600")
        self.minsize(600, 430)
        self.status = tk.StringVar(value="「情報を取得」を押してください。")
        self.rows: list[tuple[str, str]] = []
        self.events: queue.Queue[tuple[list[tuple[str, str]] | None, str | None]] = queue.Queue()
        self.cancel = threading.Event()
        self.running = False

        top = ttk.Frame(self, padding=16)
        top.pack(fill="x")
        ttk.Label(top, text="このPCの概要", font=("Segoe UI", 18, "bold")).pack(anchor="w")
        ttk.Label(top, text="OS・CPU・GPU・メモリ・ドライブ容量・画面解像度を表示します。").pack(anchor="w", pady=(6, 0))
        ttk.Label(top, text="ユーザー名・端末名・シリアル番号は表示しません。").pack(anchor="w", pady=(2, 0))

        actions = ttk.Frame(self, padding=(16, 4, 16, 12))
        actions.pack(fill="x")
        self.fetch_button = ttk.Button(actions, text="情報を取得", command=self.start)
        self.fetch_button.pack(side="left")
        self.stop_button = ttk.Button(actions, text="停止", command=self.stop, state="disabled")
        self.stop_button.pack(side="left", padx=8)
        self.copy_button = ttk.Button(actions, text="概要をコピー", command=self.copy, state="disabled")
        self.copy_button.pack(side="left")

        table = ttk.Frame(self, padding=(16, 0, 16, 0))
        table.pack(fill="both", expand=True)
        self.tree = ttk.Treeview(table, columns=("value",), show="tree headings")
        self.tree.heading("#0", text="項目")
        self.tree.heading("value", text="内容")
        self.tree.column("#0", width=150, minwidth=110, stretch=False)
        self.tree.column("value", width=550, minwidth=260)
        scrollbar = ttk.Scrollbar(table, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)
        self.tree.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        ttk.Label(self, textvariable=self.status, padding=(16, 10)).pack(fill="x")
        self.protocol("WM_DELETE_WINDOW", self.close)

    def start(self) -> None:
        if self.running:
            return
        self.running = True
        self.cancel = threading.Event()
        self.fetch_button.configure(state="disabled")
        self.stop_button.configure(state="normal")
        self.copy_button.configure(state="disabled")
        self.status.set("取得中…")
        threading.Thread(target=self._work, args=(self.cancel,), daemon=True).start()
        self.after(50, self._drain)

    def _work(self, cancel: threading.Event) -> None:
        try:
            rows = collect(resource_dir() / "fastfetch.exe", cancel)
        except Exception as error:
            self.events.put((None, str(error)))
        else:
            self.events.put((rows, None))

    def _drain(self) -> None:
        try:
            rows, error = self.events.get_nowait()
        except queue.Empty:
            if self.running:
                self.after(50, self._drain)
        else:
            self.running = False
            self.fetch_button.configure(state="normal")
            self.stop_button.configure(state="disabled")
            if error:
                self.show_rows([], error)
            else:
                self.show_rows(rows or [], "取得完了。")

    def show_rows(self, rows: list[tuple[str, str]], status: str) -> None:
        for item in self.tree.get_children():
            self.tree.delete(item)
        self.rows = rows
        for key, value in rows:
            self.tree.insert("", "end", text=key, values=(value,))
        self.copy_button.configure(state="normal" if rows else "disabled")
        self.status.set(status)

    def copy(self) -> None:
        if not self.rows:
            return
        self.clipboard_clear()
        self.clipboard_append("\n".join(f"{key}: {value}" for key, value in self.rows))
        self.status.set("表示中の概要をコピーしました。")

    def stop(self) -> None:
        self.cancel.set()
        self.status.set("停止中…")

    def close(self) -> None:
        self.cancel.set()
        self.destroy()


if __name__ == "__main__":
    if sys.argv[1:] == ["--self-test"]:
        try:
            collect(resource_dir() / "fastfetch.exe", threading.Event())
        except Exception:
            raise SystemExit(1)
    else:
        App().mainloop()
