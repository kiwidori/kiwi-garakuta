"""Kiwi Disk: a read-only Windows GUI for dust."""

from __future__ import annotations

import json
import os
import queue
import re
import subprocess
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

MAX_NODES = 200
MAX_OUTPUT_BYTES = 1_000_000
SCAN_TIMEOUT_SECONDS = 300
SIZE = re.compile(r"^([0-9]+)B$")


def resource_dir() -> Path:
    return Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))


def command(dust: Path, folder: Path, depth: int) -> list[str]:
    return [str(dust), "-j", "-P", "-n", "60", "-d", str(depth), "-o", "b", str(folder)]


def parse_size(value: object) -> int:
    match = SIZE.fullmatch(value) if isinstance(value, str) else None
    if not match:
        raise ValueError("容量データの形式が予期しないものです。")
    return int(match.group(1))


def parse_result(data: bytes) -> dict:
    if len(data) > MAX_OUTPUT_BYTES:
        raise ValueError("解析結果が大きすぎます。")
    result = json.loads(data.decode("utf-8-sig"))
    if not isinstance(result, dict) or not isinstance(result.get("name"), str):
        raise ValueError("解析結果の形式が予期しないものです。")
    parse_size(result.get("size"))
    if not isinstance(result.get("children"), list):
        raise ValueError("解析結果のツリーが予期しないものです。")
    return result


def human_size(value: int) -> str:
    for unit in ("B", "KiB", "MiB", "GiB", "TiB"):
        if value < 1024 or unit == "TiB":
            return f"{value:,} B" if unit == "B" else f"{value:.1f} {unit}"
        value /= 1024
    raise AssertionError("unreachable")


class App(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("きうい容量ビュー")
        self.geometry("1000x680")
        self.minsize(700, 450)
        self.events: queue.Queue[tuple] = queue.Queue()
        self.process: subprocess.Popen | None = None
        self.run_id = 0
        self.cancelled = False
        self.paths: dict[str, Path] = {}
        self.folder = tk.StringVar(value=str(Path.home()))
        self.depth = tk.StringVar(value="3")
        self.status = tk.StringVar(value="調べるフォルダーを選んでください。")

        top = ttk.Frame(self, padding=14)
        top.pack(fill="x")
        ttk.Label(top, text="調べるフォルダー").grid(row=0, column=0, sticky="w")
        ttk.Entry(top, textvariable=self.folder).grid(row=0, column=1, columnspan=3, sticky="ew", padx=8)
        ttk.Button(top, text="選択…", command=self.choose_folder).grid(row=0, column=4)
        ttk.Label(top, text="表示する階層").grid(row=1, column=0, sticky="w", pady=12)
        ttk.Spinbox(top, from_=1, to=6, textvariable=self.depth, width=5).grid(row=1, column=1, sticky="w", padx=8)
        self.start_button = ttk.Button(top, text="解析", command=self.start_scan)
        self.start_button.grid(row=1, column=2, sticky="ew", padx=8)
        self.stop_button = ttk.Button(top, text="停止", command=self.stop_scan, state="disabled")
        self.stop_button.grid(row=1, column=3, sticky="ew")
        ttk.Button(top, text="選択した場所を開く", command=self.open_selected).grid(row=1, column=4, padx=(8, 0))
        top.columnconfigure(1, weight=1)
        top.columnconfigure(2, weight=1)

        results = ttk.Frame(self, padding=(14, 0, 14, 0))
        results.pack(fill="both", expand=True)
        self.tree = ttk.Treeview(results, columns=("size", "percent", "bar"), show="tree headings")
        self.tree.heading("#0", text="ファイル・フォルダー")
        self.tree.heading("size", text="容量")
        self.tree.heading("percent", text="全体比")
        self.tree.heading("bar", text="割合")
        self.tree.column("#0", width=500, minwidth=220)
        self.tree.column("size", width=130, minwidth=90, anchor="e", stretch=False)
        self.tree.column("percent", width=80, minwidth=70, anchor="e", stretch=False)
        self.tree.column("bar", width=160, minwidth=100, stretch=False)
        yscroll = ttk.Scrollbar(results, orient="vertical", command=self.tree.yview)
        xscroll = ttk.Scrollbar(results, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=yscroll.set, xscrollcommand=xscroll.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        yscroll.grid(row=0, column=1, sticky="ns")
        xscroll.grid(row=1, column=0, sticky="ew")
        results.rowconfigure(0, weight=1)
        results.columnconfigure(0, weight=1)
        self.tree.bind("<Double-1>", self.open_selected)
        ttk.Label(self, text="読み取り専用です。ファイルの削除や変更は行いません。", padding=(14, 8)).pack(anchor="w")
        ttk.Label(self, textvariable=self.status, padding=(14, 0, 14, 12)).pack(fill="x")
        self.after(80, self.drain_events)
        self.protocol("WM_DELETE_WINDOW", self.close)

    def choose_folder(self) -> None:
        chosen = filedialog.askdirectory(initialdir=self.folder.get())
        if chosen:
            self.folder.set(chosen)

    def start_scan(self) -> None:
        folder = Path(self.folder.get()).expanduser()
        if not folder.is_dir():
            messagebox.showwarning("フォルダーを確認してください", "存在するフォルダーを選んでください。")
            return
        try:
            depth = int(self.depth.get())
            if not 1 <= depth <= 6:
                raise ValueError
        except ValueError:
            messagebox.showwarning("階層を確認してください", "1〜6の数値を入力してください。")
            return
        dust = resource_dir() / "dust.exe"
        if not dust.is_file():
            messagebox.showerror("dust.exe がありません", "配布ZIPを展開し直してください。")
            return
        self.run_id += 1
        run_id = self.run_id
        self.cancelled = False
        self.paths.clear()
        self.tree.delete(*self.tree.get_children())
        self.start_button.configure(state="disabled")
        self.stop_button.configure(state="normal")
        self.status.set("解析中… 大きなフォルダーでは時間がかかります。")
        threading.Thread(target=self.run_scan, args=(run_id, command(dust, folder.resolve(), depth)), daemon=True).start()

    def run_scan(self, run_id: int, args: list[str]) -> None:
        process: subprocess.Popen | None = None
        try:
            process = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                       creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            self.process = process
            if self.cancelled:
                process.terminate()
            try:
                out, err = process.communicate(timeout=SCAN_TIMEOUT_SECONDS)
            except subprocess.TimeoutExpired:
                process.kill()
                process.communicate()
                self.events.put((run_id, "error", "解析が5分を超えたため停止しました。"))
                return
            if self.cancelled:
                self.events.put((run_id, "cancelled"))
            elif process.returncode != 0:
                self.events.put((run_id, "error", err.decode("utf-8", "replace")[:1000] or
                                 f"dust の終了コード: {process.returncode}"))
            else:
                self.events.put((run_id, "result", parse_result(out), err.decode("utf-8", "replace")[:300]))
        except (OSError, ValueError, UnicodeError, json.JSONDecodeError) as exc:
            self.events.put((run_id, "error", str(exc)))
        finally:
            if self.process is process:
                self.process = None

    def show_result(self, node: dict) -> None:
        total = parse_size(node["size"])
        shown = 0

        def add(current: dict, parent: str) -> None:
            nonlocal shown
            if shown >= MAX_NODES:
                return
            if not isinstance(current, dict) or not isinstance(current.get("name"), str):
                raise ValueError("解析結果に不正な項目があります。")
            size = parse_size(current.get("size"))
            children = current.get("children")
            if not isinstance(children, list):
                raise ValueError("解析結果に不正な子項目があります。")
            path = Path(current["name"])
            percent = 100 * size / total if total else 0
            label = path.name or str(path)
            bar = "█" * min(20, round(percent / 5))
            item = self.tree.insert(parent, "end", text=label,
                                    values=(human_size(size), f"{percent:.1f}%", bar), open=(shown < 3))
            self.paths[item] = path
            shown += 1
            for child in children:
                add(child, item)

        add(node, "")
        self.status.set(f"解析完了: {human_size(total)}、表示 {shown}項目")

    def drain_events(self) -> None:
        try:
            while True:
                event = self.events.get_nowait()
                if event[0] != self.run_id:
                    continue
                self.start_button.configure(state="normal")
                self.stop_button.configure(state="disabled")
                if event[1] == "result":
                    try:
                        self.show_result(event[2])
                        if event[3].strip():
                            self.status.set(self.status.get() + "（一部にアクセスできない可能性があります）")
                    except ValueError as exc:
                        self.status.set("解析結果を表示できませんでした。")
                        messagebox.showerror("解析結果エラー", str(exc))
                elif event[1] == "cancelled":
                    self.status.set("解析を停止しました。")
                elif event[1] == "error":
                    self.status.set("解析に失敗しました。")
                    messagebox.showerror("解析エラー", event[2])
        except queue.Empty:
            pass
        self.after(80, self.drain_events)

    def stop_scan(self) -> None:
        self.cancelled = True
        if self.process and self.process.poll() is None:
            try:
                self.process.terminate()
            except OSError:
                pass
        self.status.set("停止中…")

    def open_selected(self, _: tk.Event | None = None) -> None:
        selected = self.tree.selection()
        if selected:
            path = self.paths.get(selected[0])
            if path and path.exists():
                try:
                    os.startfile(path if path.is_dir() else path.parent)
                except OSError as exc:
                    messagebox.showerror("開けませんでした", str(exc))

    def close(self) -> None:
        if self.process and self.process.poll() is None:
            try:
                self.process.terminate()
            except OSError:
                pass
        self.destroy()


if __name__ == "__main__":
    App().mainloop()
