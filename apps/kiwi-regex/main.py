import sys as _advanced_sys
from pathlib import Path as _AdvancedPath
if not getattr(_advanced_sys, "frozen", False):
    _advanced_sys.path.insert(0, str(_AdvancedPath(__file__).resolve().parents[1] / "common"))
from advanced import attach
import os
import time
import sys
import shutil
import queue
import tempfile
import threading
import subprocess
import tkinter as tk
from tkinter import ttk
from pathlib import Path
from typing import List, Optional


MAX_INPUT_BYTES = 16 * 1024
MAX_EXAMPLES = 100
MAX_EXAMPLE_CHARS = 256
MAX_OUTPUT_BYTES = 64 * 1024
GREX_TIMEOUT_SECONDS = 15
GREX_EXE_NAME = "grex.exe"


def resource_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS)
    return Path(__file__).resolve().parent


def validated_examples(text: str) -> List[str]:
    if not isinstance(text, str):
        raise ValueError("文字列を入力してください。")
    if len(text.encode('utf-8')) > MAX_INPUT_BYTES:
        raise ValueError("入力はUTF-8で16 KiBまでです。")
    if "\x00" in text:
        raise ValueError("NUL文字は入力できません。")
    normalized = text.replace("\r\n", "\n")
    if "\r" in normalized:
        raise ValueError("単独のCR文字は入力できません。")
    if not normalized:
        raise ValueError("例を1行ずつ入力してください。")
    raw_lines = normalized.split("\n")
    examples: List[str] = []
    for line in raw_lines:
        if line == "":
            continue
        if len(line) > MAX_EXAMPLE_CHARS:
            raise ValueError("1行256文字までにしてください。")
        examples.append(line)
    if not examples:
        raise ValueError("例を1行ずつ入力してください。")
    if len(examples) > MAX_EXAMPLES:
        raise ValueError("例は100行までにしてください。")
    encoded = "\n".join(examples).encode("utf-8")
    if len(encoded) > MAX_INPUT_BYTES:
        raise ValueError("入力はUTF-8で16 KiBまでです。")
    return examples


def _sanitize_error(exc: Exception) -> str:
    if isinstance(exc, InterruptedError):
        return "生成を停止しました。"
    if isinstance(exc, TimeoutError):
        return "15秒を超えたため停止しました。例を減らしてください。"
    if isinstance(exc, ValueError) and not isinstance(exc, UnicodeError):
        return str(exc)
    if isinstance(exc, FileNotFoundError):
        return "同梱のgrex.exeが見つかりません。"
    return "生成に失敗しました。"


def _run_grex(
    exe: Path,
    examples: List[str],
    digits: bool,
    ignore_case: bool,
    repetitions: bool,
    cancel: threading.Event,
) -> str:
    if cancel.is_set():
        raise InterruptedError()
    if not exe.is_file():
        raise FileNotFoundError("grex.exe not found")

    tmp_dir = Path(tempfile.mkdtemp(prefix="kiwi-regex-"))
    input_file = tmp_dir / "examples.txt"
    stdout_file = tmp_dir / "stdout.txt"
    stderr_file = tmp_dir / "stderr.txt"

    try:
        input_file.write_text("\n".join(examples), encoding="utf-8")

        cmd = [str(exe.resolve()), "--file", str(input_file)]
        if digits:
            cmd.append("--digits")
        if ignore_case:
            cmd.append("--ignore-case")
        if repetitions:
            cmd.append("--repetitions")

        with open(stdout_file, "wb") as out_fh, open(stderr_file, "wb") as err_fh:
            proc = subprocess.Popen(
                cmd,
                stdout=out_fh,
                stderr=err_fh,
                stdin=subprocess.DEVNULL,
                cwd=str(tmp_dir),
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )

            try:
                deadline = time.monotonic() + GREX_TIMEOUT_SECONDS
                while proc.poll() is None:
                    if cancel.is_set():
                        raise InterruptedError()
                    if time.monotonic() > deadline:
                        raise TimeoutError()
                    if max(stdout_file.stat().st_size, stderr_file.stat().st_size) > MAX_OUTPUT_BYTES:
                        raise ValueError("出力が64 KiBを超えたため停止しました。")
                    time.sleep(0.05)
            finally:
                if proc.poll() is None:
                    proc.kill()
                proc.wait()

            if cancel.is_set():
                raise InterruptedError("cancelled")

            if proc.returncode != 0:
                raise RuntimeError("nonzero exit")

            raw = stdout_file.read_bytes()
            if len(raw) > MAX_OUTPUT_BYTES:
                raise ValueError("出力が64 KiBを超えました。例を減らしてください。")

            text = raw.decode("utf-8")
            text = text.removesuffix("\n").removesuffix("\r")
            if not text:
                raise RuntimeError('empty output')
            return text
    finally:
        if tmp_dir.resolve().parent == Path(tempfile.gettempdir()).resolve() and tmp_dir.name.startswith('kiwi-regex-'):
            shutil.rmtree(tmp_dir, ignore_errors=True)


def generate(
    exe: Path,
    text: str,
    digits: bool,
    ignore_case: bool,
    repetitions: bool,
    cancel: threading.Event,
) -> str:
    examples = validated_examples(text)
    return _run_grex(exe, examples, digits, ignore_case, repetitions, cancel)


class App(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("きうい正規表現")
        self.geometry("900x620")
        self.minsize(720, 480)

        self.status = tk.StringVar(value="準備完了")
        self.running = False

        self._cancel_event = threading.Event()
        self._worker: Optional[threading.Thread] = None
        self._result_queue: "queue.Queue[tuple[str, Optional[str]]]" = queue.Queue()

        self._build_ui()
        self.protocol("WM_DELETE_WINDOW", self.close)
        # Additional upstream operations run in a separate structured window.
        self.advanced = attach(self, source_dir=Path(__file__).resolve().parent)

    def _build_ui(self) -> None:
        main = ttk.Frame(self, padding=10)
        main.pack(fill=tk.BOTH, expand=True)

        input_label = ttk.Label(main, text="入力例（1行1件）")
        input_label.pack(anchor=tk.W)
        ttk.Label(main, text="生成結果は、実際に使う正規表現エンジンで確認してください。").pack(anchor=tk.W)

        self.examples = tk.Text(main, height=10, wrap=tk.WORD)
        self.examples.pack(fill=tk.BOTH, expand=True, pady=(4, 8))

        options = ttk.Frame(main)
        options.pack(fill=tk.X, pady=(0, 8))

        self.digits_var = tk.BooleanVar(value=False)
        self.ignore_case_var = tk.BooleanVar(value=False)
        self.repetitions_var = tk.BooleanVar(value=False)

        ttk.Checkbutton(options, text="数字を一般化", variable=self.digits_var).pack(side=tk.LEFT, padx=(0, 12))
        ttk.Checkbutton(options, text="大小文字を区別しない", variable=self.ignore_case_var).pack(side=tk.LEFT, padx=(0, 12))
        ttk.Checkbutton(options, text="繰り返しをまとめる", variable=self.repetitions_var).pack(side=tk.LEFT)

        buttons = ttk.Frame(main)
        buttons.pack(fill=tk.X, pady=(0, 8))

        self.generate_btn = ttk.Button(buttons, text="生成", command=self.start_generate)
        self.generate_btn.pack(side=tk.LEFT, padx=(0, 8))

        self.cancel_btn = ttk.Button(buttons, text="停止", command=self.stop_generate, state=tk.DISABLED)
        self.cancel_btn.pack(side=tk.LEFT, padx=(0, 8))

        self.copy_btn = ttk.Button(buttons, text="コピー", command=self._copy_output, state=tk.DISABLED)
        self.copy_btn.pack(side=tk.LEFT)

        output_label = ttk.Label(main, text="出力")
        output_label.pack(anchor=tk.W)

        self.output = tk.Text(main, height=8, wrap=tk.WORD, state=tk.DISABLED)
        self.output.pack(fill=tk.BOTH, expand=True, pady=(4, 8))

        status_bar = ttk.Label(main, textvariable=self.status, anchor=tk.W, relief=tk.SUNKEN)
        status_bar.pack(fill=tk.X)

    def _set_running(self, running: bool) -> None:
        self.running = running
        if running:
            self.generate_btn.config(state=tk.DISABLED)
            self.cancel_btn.config(state=tk.NORMAL)
            self.copy_btn.config(state=tk.DISABLED)
            self.examples.config(state=tk.DISABLED)
        else:
            self.generate_btn.config(state=tk.NORMAL)
            self.cancel_btn.config(state=tk.DISABLED)
            self.examples.config(state=tk.NORMAL)
            if self.output.get("1.0", tk.END).strip():
                self.copy_btn.config(state=tk.NORMAL)
            else:
                self.copy_btn.config(state=tk.DISABLED)

    def _clear_output(self) -> None:
        self.output.config(state=tk.NORMAL)
        self.output.delete("1.0", tk.END)
        self.output.config(state=tk.DISABLED)
        self.copy_btn.config(state=tk.DISABLED)

    def _copy_output(self) -> None:
        if self.running:
            return
        text = self.output.get("1.0", tk.END)
        if text.endswith("\n"):
            text = text[:-1]
        self.clipboard_clear()
        self.clipboard_append(text)
        self.status.set("コピーしました")

    def _worker_target(
        self,
        exe: Path,
        text: str,
        digits: bool,
        ignore_case: bool,
        repetitions: bool,
        cancel: threading.Event,
    ) -> None:
        try:
            result = generate(exe, text, digits, ignore_case, repetitions, cancel)
            self._result_queue.put(("ok", result))
        except Exception as exc:
            self._result_queue.put(("error", _sanitize_error(exc)))

    def start_generate(self) -> None:
        if self.running:
            return

        text = self.examples.get("1.0", tk.END)
        if text.endswith("\n"):
            text = text[:-1]

        self._clear_output()
        self.status.set("生成中...")
        self._cancel_event.clear()
        self._set_running(True)

        exe = resource_dir() / GREX_EXE_NAME
        self._worker = threading.Thread(
            target=self._worker_target,
            args=(
                exe,
                text,
                self.digits_var.get(),
                self.ignore_case_var.get(),
                self.repetitions_var.get(),
                self._cancel_event,
            ),
            daemon=True,
        )
        self._worker.start()
        self.after(50, self._poll_results)

    def stop_generate(self) -> None:
        if not self.running:
            return
        self._cancel_event.set()
        self.status.set("停止中...")

    def _poll_results(self) -> None:
        try:
            kind, payload = self._result_queue.get_nowait()
        except queue.Empty:
            if self.running:
                self.after(50, self._poll_results)
            return

        self._set_running(False)

        if kind == "ok":
            self.output.config(state=tk.NORMAL)
            self.output.insert("1.0", payload)
            self.output.config(state=tk.DISABLED)
            if payload:
                self.copy_btn.config(state=tk.NORMAL)
            self.status.set("生成しました")
        else:
            self.status.set(payload or "生成に失敗しました。")

        if self.running:
            self.after(50, self._poll_results)

    def close(self) -> None:
        if self.running:
            self._cancel_event.set()
            if self._worker is not None:
                self._worker.join(timeout=2)
        self.destroy()


def main() -> None:
    app = App()
    app.mainloop()


if __name__ == "__main__":
    main()
