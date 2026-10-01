"""Kiwi HTTP: a GUI for explicit xh GET/HEAD requests."""
import tkinter as tk
from tkinter import ttk
import threading
import queue
from pathlib import Path
from core import request, resource_dir, validate_url

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("きういHTTPビュー")
        self.geometry("980x620")
        self.minsize(720, 420)

        self.url = tk.StringVar()
        self.method = tk.StringVar(value="GET")
        self.status = tk.StringVar(value="待機中")
        self.running = False

        self._cancel_event = threading.Event()
        self._worker = None
        self._queue = queue.Queue()

        self._build_ui()
        self._poll_queue()
        self.protocol("WM_DELETE_WINDOW", self.close)

    def _build_ui(self):
        top = ttk.Frame(self, padding=8)
        top.pack(fill="x")

        ttk.Label(top, text="URL:").grid(row=0, column=0, sticky="w")
        self._url_entry = ttk.Entry(top, textvariable=self.url)
        self._url_entry.grid(row=0, column=1, columnspan=2, sticky="ew", padx=4)
        top.columnconfigure(1, weight=1)

        ttk.Label(top, text="メソッド:").grid(row=1, column=0, sticky="w", pady=(4, 0))
        self._method_combo = ttk.Combobox(top, textvariable=self.method, values=["GET", "HEAD"], state="readonly", width=10)
        self._method_combo.grid(row=1, column=1, sticky="w", padx=4, pady=(4, 0))

        btn_frame = ttk.Frame(top)
        btn_frame.grid(row=0, column=3, rowspan=2, padx=(8, 0))
        self._send_btn = ttk.Button(btn_frame, text="送信", command=self.start_request)
        self._send_btn.pack(side="left", padx=2)
        self._stop_btn = ttk.Button(btn_frame, text="停止", command=self.stop_request, state="disabled")
        self._stop_btn.pack(side="left", padx=2)
        self._copy_btn = ttk.Button(btn_frame, text="コピー", command=self.copy_output, state="disabled")
        self._copy_btn.pack(side="left", padx=2)

        mid = ttk.Frame(self, padding=8)
        mid.pack(fill="both", expand=True)

        self.output = tk.Text(mid, wrap="none", state="disabled", font=("Consolas", 10))
        sb = ttk.Scrollbar(mid, orient="vertical", command=self.output.yview)
        self.output.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        self.output.pack(side="left", fill="both", expand=True)
        horizontal = ttk.Scrollbar(self, orient="horizontal", command=self.output.xview)
        horizontal.pack(fill="x", padx=8)
        self.output.configure(xscrollcommand=horizontal.set)

        notice = ttk.Label(self, text="入力したURLへ通信します。URLや応答の共有時は個人情報に注意してください。リダイレクトは追跡しません。", wraplength=690, foreground="#555")
        notice.pack(fill="x", padx=8, pady=(0, 4))

        status_bar = ttk.Label(self, textvariable=self.status, relief="sunken", anchor="w", padding=(6, 2))
        status_bar.pack(fill="x", side="bottom")

        self.url.trace_add("write", lambda *a: self._on_url_change())

    def _on_url_change(self):
        if not self.running:
            self._clear_output()

    def _clear_output(self):
        self.output.configure(state="normal")
        self.output.delete("1.0", "end")
        self.output.configure(state="disabled")
        self._copy_btn.configure(state="disabled")

    def _set_output(self, text):
        self.output.configure(state="normal")
        self.output.insert("1.0", text)
        self.output.configure(state="disabled")
        self._copy_btn.configure(state="normal")

    def start_request(self):
        if self.running:
            return
        url = self.url.get().strip()
        method = self.method.get()
        try:
            validate_url(url)
        except ValueError as e:
            self.status.set(str(e))
            return

        self.running = True
        self._cancel_event.clear()
        self._send_btn.configure(state="disabled")
        self._url_entry.configure(state="disabled")
        self._method_combo.configure(state="disabled")
        self._stop_btn.configure(state="normal")
        self._copy_btn.configure(state="disabled")
        self._clear_output()
        self.status.set("リクエスト中...")

        self._worker = threading.Thread(
            target=self._worker_fn,
            args=(resource_dir() / 'xh.exe', url, method, self._cancel_event),
            daemon=True
        )
        self._worker.start()

    def _worker_fn(self, exe, url, method, cancel_event):
        try:
            result = request(exe, url, method, cancel_event)
            self._queue.put(("result", result))
        except InterruptedError:
            self._queue.put(("error", "送信を停止しました。"))
        except TimeoutError:
            self._queue.put(("error", "15秒を超えたため停止しました。"))
        except ValueError as error:
            self._queue.put(("error", str(error)))
        except Exception:
            self._queue.put(("error", "リクエスト中にエラーが発生しました。"))

    def stop_request(self):
        if self.running:
            self._cancel_event.set()
            self.status.set("停止中...")

    def copy_output(self):
        if self.running:
            return
        content = self.output.get("1.0", "end-1c")
        if content:
            self.clipboard_clear()
            self.clipboard_append(content)
            self.status.set("コピーしました。")

    def _poll_queue(self):
        try:
            while True:
                kind, payload = self._queue.get_nowait()
                if kind == "result":
                    self._set_output(payload)
                    self.status.set("完了")
                elif kind == "error":
                    self.status.set(payload)
                self.running = False
                self._send_btn.configure(state="normal")
                self._url_entry.configure(state="normal")
                self._method_combo.configure(state="readonly")
                self._stop_btn.configure(state="disabled")
                if self._worker:
                    self._worker = None
        except queue.Empty:
            pass
        self.after(100, self._poll_queue)

    def close(self):
        if self.running:
            self._cancel_event.set()
            if self._worker:
                self._worker.join(timeout=2)
        self.destroy()


if __name__ == '__main__':
    App().mainloop()
