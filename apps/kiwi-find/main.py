"""Kiwi Find: a small, unofficial Windows GUI for fd."""

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
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

MAX_RESULTS = 1000


def resource_dir() -> Path:
    return Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))


def command(fd: Path, phrase: str, folder: Path, extension: str,
            hidden: bool, ignored: bool) -> list[str]:
    args = [str(fd), "--fixed-strings", "--absolute-path", "--print0", "--color", "never", "--type", "file"]
    if extension:
        args += ["--extension", extension.lstrip(".")]
    if hidden:
        args.append("--hidden")
    if ignored:
        args.append("--no-ignore")
    args += ["--", phrase, str(folder)]
    return args


class App(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("きういファイル探し")
        self.geometry("950x630")
        self.minsize(690, 420)
        self.events: queue.Queue[tuple] = queue.Queue()
        self.process: subprocess.Popen | None = None
        self.run_id = 0
        self.count = 0
        self.folder = tk.StringVar(value=str(Path.home()))
        self.phrase = tk.StringVar()
        self.extension = tk.StringVar()
        self.hidden = tk.BooleanVar(value=False)
        self.ignored = tk.BooleanVar(value=False)
        self.status = tk.StringVar(value="フォルダーとファイル名の一部を指定してください。")

        top = ttk.Frame(self, padding=14)
        top.pack(fill="x")
        ttk.Label(top, text="探すフォルダー").grid(row=0, column=0, sticky="w")
        ttk.Entry(top, textvariable=self.folder).grid(row=0, column=1, columnspan=2, sticky="ew", padx=8)
        ttk.Button(top, text="選択…", command=self.choose_folder).grid(row=0, column=3)
        ttk.Label(top, text="名前に含む文字").grid(row=1, column=0, sticky="w", pady=12)
        entry = ttk.Entry(top, textvariable=self.phrase)
        entry.grid(row=1, column=1, sticky="ew", padx=8)
        entry.bind("<Return>", lambda _: self.start_search())
        ttk.Label(top, text="拡張子").grid(row=1, column=2, sticky="e")
        ttk.Entry(top, textvariable=self.extension, width=12).grid(row=1, column=3, sticky="ew", padx=(8, 0))
        ttk.Checkbutton(top, text="隠しファイルを含める", variable=self.hidden).grid(row=2, column=1, sticky="w")
        ttk.Checkbutton(top, text="除外設定を無視", variable=self.ignored).grid(row=2, column=2, columnspan=2, sticky="w")
        self.start_button = ttk.Button(top, text="検索", command=self.start_search)
        self.start_button.grid(row=3, column=1, sticky="ew", padx=8, pady=(12, 0))
        self.stop_button = ttk.Button(top, text="停止", command=self.stop_search, state="disabled")
        self.stop_button.grid(row=3, column=2, sticky="ew", pady=(12, 0))
        top.columnconfigure(1, weight=1)

        results = ttk.Frame(self, padding=(14, 0, 14, 0))
        results.pack(fill="both", expand=True)
        self.tree = ttk.Treeview(results, columns=("name", "folder"), show="headings")
        self.tree.heading("name", text="ファイル名")
        self.tree.heading("folder", text="場所")
        self.tree.column("name", width=260, minwidth=120)
        self.tree.column("folder", width=640, minwidth=200)
        scrollbar = ttk.Scrollbar(results, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)
        self.tree.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        self.tree.bind("<Double-1>", self.open_file)
        ttk.Label(self, text="ダブルクリックでファイルを開きます。", padding=(14, 8)).pack(anchor="w")
        ttk.Label(self, textvariable=self.status, padding=(14, 0, 14, 12)).pack(fill="x")
        self.after(80, self.drain_events)
        self.protocol("WM_DELETE_WINDOW", self.close)
        entry.focus_set()
        # Additional upstream operations run in a separate structured window.
        self.advanced = attach(self, source_dir=Path(__file__).resolve().parent)

    def choose_folder(self) -> None:
        chosen = filedialog.askdirectory(initialdir=self.folder.get())
        if chosen:
            self.folder.set(chosen)

    def start_search(self) -> None:
        folder = Path(self.folder.get())
        if not folder.is_dir():
            messagebox.showwarning("フォルダーを確認してください", "存在するフォルダーを選んでください。")
            return
        ext = self.extension.get().strip()
        if ext and (any(char in ext for char in "\\/\r\n\0*") or ext in (".", "..")):
            messagebox.showwarning("拡張子を確認してください", "拡張子だけを入力してください。例: txt")
            return
        fd = resource_dir() / "fd.exe"
        if not fd.is_file():
            messagebox.showerror("fd.exe がありません", "配布ZIPを展開し直してください。")
            return
        self.stop_search()
        self.run_id += 1
        run_id = self.run_id
        self.count = 0
        self.tree.delete(*self.tree.get_children())
        self.start_button.configure(state="disabled")
        self.stop_button.configure(state="normal")
        self.status.set("検索中…")
        args = command(fd, self.phrase.get(), folder, ext, self.hidden.get(), self.ignored.get())
        threading.Thread(target=self.run_search, args=(run_id, args), daemon=True).start()

    def run_search(self, run_id: int, args: list[str]) -> None:
        process: subprocess.Popen | None = None
        try:
            process = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                       creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            self.process = process
            assert process.stdout is not None
            buffer = b""
            count = 0
            limited = False
            while chunk := process.stdout.read(4096):
                buffer += chunk
                parts = buffer.split(b"\0")
                buffer = parts.pop()
                for raw in parts:
                    if not raw:
                        continue
                    self.events.put((run_id, "match", os.fsdecode(raw)))
                    count += 1
                    if count >= MAX_RESULTS:
                        limited = True
                        process.terminate()
                        break
                if limited:
                    break
            code = process.wait(timeout=5)
            error = process.stderr.read().decode("utf-8", "replace") if process.stderr else ""
            self.events.put((run_id, "done", code, limited, error))
        except (OSError, subprocess.TimeoutExpired) as exc:
            if process and process.poll() is None:
                process.kill()
            self.events.put((run_id, "error", str(exc)))
        finally:
            if self.process is process:
                self.process = None

    def drain_events(self) -> None:
        try:
            while True:
                event = self.events.get_nowait()
                if event[0] != self.run_id:
                    continue
                if event[1] == "match":
                    path = Path(event[2])
                    self.tree.insert("", "end", values=(path.name, str(path.parent)), tags=(str(path),))
                    self.count += 1
                elif event[1] == "done":
                    self.start_button.configure(state="normal")
                    self.stop_button.configure(state="disabled")
                    if event[3]:
                        self.status.set(f"{MAX_RESULTS}件に達したため停止しました。")
                    elif event[2] != 0:
                        self.status.set("検索に失敗しました。")
                        messagebox.showerror("検索エラー", event[4] or f"fd の終了コード: {event[2]}")
                    else:
                        self.status.set(f"検索完了: {self.count}件")
                elif event[1] == "error":
                    self.start_button.configure(state="normal")
                    self.stop_button.configure(state="disabled")
                    self.status.set("検索に失敗しました。")
                    messagebox.showerror("検索エラー", event[2])
        except queue.Empty:
            pass
        self.after(80, self.drain_events)

    def stop_search(self) -> None:
        if self.process and self.process.poll() is None:
            self.process.terminate()

    def open_file(self, _: tk.Event) -> None:
        selected = self.tree.selection()
        if selected:
            path = Path(self.tree.item(selected[0], "tags")[0])
            if path.is_file():
                os.startfile(path)

    def close(self) -> None:
        self.stop_search()
        self.destroy()


if __name__ == "__main__":
    App().mainloop()
