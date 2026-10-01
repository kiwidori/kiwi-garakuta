"""Kiwi Code: a read-only, unofficial GUI for bat."""

from __future__ import annotations

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
from tkinter import filedialog, ttk

MAX_INPUT_BYTES = 10 * 1024 * 1024
MAX_OUTPUT_BYTES = 2 * 1024 * 1024
TIMEOUT_SECONDS = 15
PAGE_LINES = 500
THEMES = {"TwoDark": ("#282c34", "#abb2bf"), "GitHub": ("#ffffff", "#24292f"), "Dracula": ("#282a36", "#f8f8f2")}
ANSI = re.compile(r"\x1b\[([0-?]*[ -/]*[@-~])")


def resource_dir() -> Path:
    return Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))


def run_bat(bat: Path, source: Path, start_line: int, theme: str, cancel: threading.Event) -> str:
    if not source.is_file():
        raise ValueError("表示するファイルを選んでください。")
    if source.stat().st_size > MAX_INPUT_BYTES:
        raise ValueError("10 MiBを超えるファイルは表示できません。")
    if start_line < 1:
        raise ValueError("開始行は1以上にしてください。")
    if theme not in THEMES:
        raise ValueError("テーマの指定が正しくありません。")
    if not bat.is_file():
        raise FileNotFoundError("同梱のbat.exeが見つかりません。")
    end_line = start_line + PAGE_LINES - 1
    command = [str(bat), "--paging=never", "--color=always", "--decorations=always",
               "--style=numbers", "--wrap=never", f"--theme={theme}",
               f"--line-range={start_line}:{end_line}", str(source)]
    with tempfile.TemporaryFile() as stdout, tempfile.TemporaryFile() as stderr:
        try:
            process = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=stdout, stderr=stderr,
                                       creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        except OSError as error:
            raise OSError("bat.exeを起動できません。Microsoft Visual C++ Redistributableの有無も確認してください。") from error
        started = time.monotonic()
        try:
            while process.poll() is None:
                if cancel.is_set():
                    raise InterruptedError("表示を停止しました。")
                if time.monotonic() - started > TIMEOUT_SECONDS:
                    raise TimeoutError("表示に15秒以上かかりました。")
                if os.fstat(stdout.fileno()).st_size > MAX_OUTPUT_BYTES:
                    raise ValueError("表示結果が2 MiBを超えました。")
                time.sleep(0.05)
        finally:
            if process.poll() is None:
                process.kill()
            process.wait()
        if os.fstat(stdout.fileno()).st_size > MAX_OUTPUT_BYTES:
            raise ValueError("表示結果が2 MiBを超えました。")
        stderr.seek(0)
        error = stderr.read(4096).decode("utf-8", errors="replace").strip()
        if process.returncode:
            raise ValueError(error or f"batが終了コード{process.returncode}を返しました。")
        stdout.seek(0)
        return stdout.read().decode("utf-8", errors="replace").replace("\r\n", "\n")


def color256(index: int) -> str:
    basic = ["#000000", "#800000", "#008000", "#808000", "#000080", "#800080", "#008080", "#c0c0c0",
             "#808080", "#ff0000", "#00ff00", "#ffff00", "#0000ff", "#ff00ff", "#00ffff", "#ffffff"]
    if 0 <= index < 16:
        return basic[index]
    if 16 <= index < 232:
        number = index - 16
        levels = (0, 95, 135, 175, 215, 255)
        red, green, blue = levels[number // 36], levels[(number // 6) % 6], levels[number % 6]
        return f"#{red:02x}{green:02x}{blue:02x}"
    if 232 <= index <= 255:
        shade = 8 + (index - 232) * 10
        return f"#{shade:02x}{shade:02x}{shade:02x}"
    return "#ffffff"


def ansi_runs(value: str):
    """Yield visible text and its current foreground color."""
    foreground = None
    position = 0
    for match in ANSI.finditer(value):
        if match.start() > position:
            yield value[position:match.start()], foreground
        code = match.group(1)
        if code.endswith("m"):
            fields = [int(part) if part.isdigit() else 0 for part in code[:-1].split(";")]
            index = 0
            while index < len(fields):
                item = fields[index]
                if item in (0, 39):
                    foreground = None
                elif item == 38 and index + 2 < len(fields) and fields[index + 1] == 5:
                    foreground = color256(fields[index + 2])
                    index += 2
                elif item == 38 and index + 4 < len(fields) and fields[index + 1] == 2:
                    red, green, blue = (max(0, min(255, number)) for number in fields[index + 2:index + 5])
                    foreground = f"#{red:02x}{green:02x}{blue:02x}"
                    index += 4
                index += 1
        position = match.end()
    if position < len(value):
        yield value[position:], foreground


class App(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("きういコードビュー")
        self.geometry("980x700")
        self.minsize(720, 450)
        self.source = tk.StringVar()
        self.start_line = tk.StringVar(value="1")
        self.theme = tk.StringVar(value="TwoDark")
        self.status = tk.StringVar(value="表示するテキストファイルを選んでください。")
        self.events: queue.Queue[tuple[str | None, str | None]] = queue.Queue()
        self.cancel = threading.Event()
        self.running = False
        self.active_theme = "TwoDark"

        controls = ttk.Frame(self, padding=14)
        controls.pack(fill="x")
        ttk.Label(controls, text="ファイル").grid(row=0, column=0, sticky="w")
        ttk.Entry(controls, textvariable=self.source).grid(row=0, column=1, columnspan=4, sticky="ew", padx=8)
        ttk.Button(controls, text="選択…", command=self.choose).grid(row=0, column=5)
        ttk.Label(controls, text="開始行").grid(row=1, column=0, sticky="w", pady=12)
        ttk.Spinbox(controls, from_=1, to=999999, textvariable=self.start_line, width=9).grid(row=1, column=1, sticky="w", padx=8)
        ttk.Label(controls, text="テーマ").grid(row=1, column=2, sticky="e")
        ttk.Combobox(controls, textvariable=self.theme, values=tuple(THEMES), state="readonly", width=15).grid(row=1, column=3, sticky="w", padx=8)
        controls.columnconfigure(4, weight=1)

        actions = ttk.Frame(self, padding=(14, 0, 14, 10))
        actions.pack(fill="x")
        self.show_button = ttk.Button(actions, text="表示", command=self.start)
        self.show_button.pack(side="left")
        self.prev_button = ttk.Button(actions, text="前の500行", command=lambda: self.move(-PAGE_LINES))
        self.prev_button.pack(side="left", padx=(8, 0))
        self.next_button = ttk.Button(actions, text="次の500行", command=lambda: self.move(PAGE_LINES))
        self.next_button.pack(side="left", padx=8)
        self.stop_button = ttk.Button(actions, text="停止", command=self.stop, state="disabled")
        self.stop_button.pack(side="left")
        ttk.Label(actions, text="読み取り専用 · 最大10 MiB").pack(side="right")

        body = ttk.Frame(self, padding=(14, 0, 14, 0))
        body.pack(fill="both", expand=True)
        self.preview = tk.Text(body, wrap="none", font=("Consolas", 10), state="disabled", relief="flat")
        ybar = ttk.Scrollbar(body, orient="vertical", command=self.preview.yview)
        xbar = ttk.Scrollbar(body, orient="horizontal", command=self.preview.xview)
        self.preview.configure(yscrollcommand=ybar.set, xscrollcommand=xbar.set)
        self.preview.grid(row=0, column=0, sticky="nsew")
        ybar.grid(row=0, column=1, sticky="ns")
        xbar.grid(row=1, column=0, sticky="ew")
        body.rowconfigure(0, weight=1)
        body.columnconfigure(0, weight=1)
        ttk.Label(self, textvariable=self.status, padding=(14, 8)).pack(fill="x")
        self.protocol("WM_DELETE_WINDOW", self.close)

    def choose(self) -> None:
        selected = filedialog.askopenfilename(filetypes=[("テキスト・コード", "*.txt *.py *.js *.json *.md *.html *.css *.rs *.go"), ("すべてのファイル", "*.*")])
        if selected:
            self.source.set(selected)
            self.start_line.set("1")

    def move(self, amount: int) -> None:
        if self.running:
            return
        try:
            current = int(self.start_line.get())
        except ValueError:
            current = 1
        self.start_line.set(str(max(1, current + amount)))
        self.start()

    def start(self) -> None:
        if self.running:
            return
        try:
            first = int(self.start_line.get())
        except ValueError:
            self.status.set("開始行を数字で入力してください。")
            return
        source = Path(self.source.get().strip())
        theme = self.theme.get()
        self.active_theme = theme
        self.cancel = threading.Event()
        self.running = True
        self.show_button.configure(state="disabled")
        self.prev_button.configure(state="disabled")
        self.next_button.configure(state="disabled")
        self.stop_button.configure(state="normal")
        self.status.set("表示中…")
        threading.Thread(target=self._work, args=(source, first, theme, self.cancel), daemon=True).start()
        self.after(50, self._drain)

    def _work(self, source: Path, first: int, theme: str, cancel: threading.Event) -> None:
        try:
            result = run_bat(resource_dir() / "bat.exe", source, first, theme, cancel)
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
        self.show_button.configure(state="normal")
        self.prev_button.configure(state="normal")
        self.next_button.configure(state="normal")
        self.stop_button.configure(state="disabled")
        if error:
            self.preview.configure(state="normal")
            self.preview.delete("1.0", "end")
            self.preview.configure(state="disabled")
            self.status.set(error)
            return
        background, foreground = THEMES[self.active_theme]
        self.preview.configure(state="normal", background=background, foreground=foreground, insertbackground=foreground)
        self.preview.delete("1.0", "end")
        known_colors = set(self.preview.tag_names())
        for fragment, color in ansi_runs(result or ""):
            if color:
                tag = "fg_" + color[1:]
                if tag not in known_colors:
                    self.preview.tag_configure(tag, foreground=color)
                    known_colors.add(tag)
                self.preview.insert("end", fragment, tag)
            else:
                self.preview.insert("end", fragment)
        self.preview.configure(state="disabled")
        self.status.set(f"表示完了: {self.start_line.get()}行目から最大{PAGE_LINES}行。")

    def stop(self) -> None:
        self.cancel.set()
        self.status.set("停止中…")

    def close(self) -> None:
        self.cancel.set()
        self.destroy()


if __name__ == "__main__":
    App().mainloop()
