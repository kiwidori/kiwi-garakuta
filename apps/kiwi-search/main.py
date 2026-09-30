"""Kiwi Search: a small Windows GUI for ripgrep."""

from __future__ import annotations

import json
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


def command(rg: Path, phrase: str, folder: Path) -> list[str]:
    return [str(rg), "--json", "--fixed-strings", "--line-number", "--color", "never", "--", phrase, str(folder)]


def match_from_json(line: str) -> tuple[str, int, str] | None:
    item = json.loads(line)
    if item.get("type") != "match":
        return None
    data = item["data"]
    return data["path"].get("text", ""), int(data["line_number"]), data["lines"].get("text", "").strip()


class App(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("きうい検索")
        self.geometry("950x650")
        self.minsize(680, 420)
        self.events: queue.Queue[tuple] = queue.Queue()
        self.process: subprocess.Popen | None = None
        self.count = 0
        self.search_folder = Path.home()
        self.folder = tk.StringVar(value=str(Path.home()))
        self.phrase = tk.StringVar()
        self.status = tk.StringVar(value="検索するフォルダーと文字列を指定してください。")

        top = ttk.Frame(self, padding=14)
        top.pack(fill="x")
        ttk.Label(top, text="フォルダー").grid(row=0, column=0, sticky="w")
        ttk.Entry(top, textvariable=self.folder).grid(row=0, column=1, sticky="ew", padx=8)
        ttk.Button(top, text="選択…", command=self.choose_folder).grid(row=0, column=2)
        ttk.Label(top, text="探す文字列").grid(row=1, column=0, sticky="w", pady=10)
        entry = ttk.Entry(top, textvariable=self.phrase)
        entry.grid(row=1, column=1, sticky="ew", padx=8)
        entry.bind("<Return>", lambda _: self.start_search())
        self.start_button = ttk.Button(top, text="検索", command=self.start_search)
        self.start_button.grid(row=1, column=2, sticky="ew")
        self.stop_button = ttk.Button(top, text="停止", command=self.stop_search, state="disabled")
        self.stop_button.grid(row=1, column=3, padx=(8, 0))
        top.columnconfigure(1, weight=1)

        results = ttk.Frame(self, padding=(14, 0, 14, 0))
        results.pack(fill="both", expand=True)
        self.tree = ttk.Treeview(results, columns=("file", "line", "text"), show="headings")
        for key, title, width in (("file", "ファイル", 330), ("line", "行", 55), ("text", "内容", 480)):
            self.tree.heading(key, text=title)
            self.tree.column(key, width=width, minwidth=45)
        self.tree.column("line", stretch=False)
        yscroll = ttk.Scrollbar(results, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=yscroll.set)
        self.tree.pack(side="left", fill="both", expand=True)
        yscroll.pack(side="right", fill="y")
        self.tree.bind("<Double-1>", self.open_file)
        ttk.Label(self, textvariable=self.status, padding=14).pack(fill="x")
        self.after(80, self.drain_events)
        self.protocol("WM_DELETE_WINDOW", self.close)
        entry.focus_set()

    def choose_folder(self) -> None:
        chosen = filedialog.askdirectory(initialdir=self.folder.get())
        if chosen:
            self.folder.set(chosen)

    def start_search(self) -> None:
        phrase = self.phrase.get()
        folder = Path(self.folder.get())
        if not phrase:
            messagebox.showwarning("入力が必要です", "探す文字列を入力してください。")
            return
        if not folder.is_dir():
            messagebox.showwarning("フォルダーを確認してください", "存在するフォルダーを選んでください。")
            return
        rg = resource_dir() / "rg.exe"
        if not rg.is_file():
            messagebox.showerror("rg.exe がありません", "配布ZIPを展開し直してください。")
            return
        self.stop_search()
        self.search_folder = folder
        self.tree.delete(*self.tree.get_children())
        self.count = 0
        self.start_button.configure(state="disabled")
        self.stop_button.configure(state="normal")
        self.status.set("検索中…")
        threading.Thread(target=self.run_search, args=(rg, phrase, folder), daemon=True).start()

    def run_search(self, rg: Path, phrase: str, folder: Path) -> None:
        try:
            process = subprocess.Popen(command(rg, phrase, folder), stdout=subprocess.PIPE,
                                       stderr=subprocess.PIPE, text=True, encoding="utf-8", errors="replace",
                                       creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            self.process = process
            assert process.stdout is not None
            matched = 0
            for line in process.stdout:
                result = match_from_json(line)
                if result:
                    path, line_number, content = result
                    self.events.put(("match", (os.path.relpath(path, folder), line_number, content)))
                    matched += 1
                    if matched >= MAX_RESULTS:
                        process.terminate()
                        self.events.put(("limit",))
                        break
            code = process.wait(timeout=5)
            self.events.put(("done", code))
        except (OSError, ValueError, subprocess.TimeoutExpired, json.JSONDecodeError) as error:
            self.events.put(("error", str(error)))
        finally:
            self.process = None

    def drain_events(self) -> None:
        try:
            while True:
                event = self.events.get_nowait()
                if event[0] == "match":
                    self.tree.insert("", "end", values=event[1])
                    self.count += 1
                elif event[0] == "limit":
                    self.status.set(f"{MAX_RESULTS}件に達したため停止しました。")
                elif event[0] == "done":
                    self.start_button.configure(state="normal")
                    self.stop_button.configure(state="disabled")
                    if self.count < MAX_RESULTS:
                        self.status.set(f"検索完了: {self.count}件")
                elif event[0] == "error":
                    self.start_button.configure(state="normal")
                    self.stop_button.configure(state="disabled")
                    self.status.set("検索に失敗しました。")
                    messagebox.showerror("検索エラー", event[1])
        except queue.Empty:
            pass
        self.after(80, self.drain_events)

    def stop_search(self) -> None:
        if self.process and self.process.poll() is None:
            self.process.terminate()

    def open_file(self, _: tk.Event) -> None:
        selected = self.tree.selection()
        if selected:
            path = str(self.search_folder / self.tree.item(selected[0], "values")[0])
            if os.path.isfile(path):
                os.startfile(path)

    def close(self) -> None:
        self.stop_search()
        self.destroy()


if __name__ == "__main__":
    App().mainloop()
