"""Kiwi Hash: file BLAKE3 calculation and comparison."""
import sys as _advanced_sys
from pathlib import Path as _AdvancedPath
if not getattr(_advanced_sys, "frozen", False):
    _advanced_sys.path.insert(0, str(_AdvancedPath(__file__).resolve().parents[1] / "common"))
from advanced import attach
import tkinter as tk
from tkinter import ttk,filedialog
import threading
import queue
from pathlib import Path
from core import hash_file,normalize_expected,resource_dir

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("きういハッシュ")
        self.geometry("900x360")
        self.minsize(800, 340)

        self.source = tk.StringVar()
        self.expected = tk.StringVar()
        self.digest = tk.StringVar()
        self.status = tk.StringVar(value="待機中")
        self.running = False

        self._cancel = threading.Event()
        self._worker_thread = None
        self._q = queue.Queue()

        self._build_ui()
        self.source.trace_add('write', lambda *args: self._on_input_change())
        self.expected.trace_add('write', lambda *args: self._on_input_change())
        self.protocol("WM_DELETE_WINDOW", self.close)
        self.after(100, self._poll_queue)
        # Additional upstream operations run in a separate structured window.
        self.advanced = attach(self, source_dir=Path(__file__).resolve().parent)

    def _build_ui(self):
        pad = {"padx": 8, "pady": 4}
        frm = ttk.Frame(self)
        frm.pack(fill="both", expand=True, padx=10, pady=10)

        ttk.Label(frm, text="対象ファイル:").grid(row=0, column=0, sticky="w", **pad)
        self._src_entry = ttk.Entry(frm, textvariable=self.source)
        self._src_entry.grid(row=0, column=1, sticky="ew", **pad)
        self._btn_pick = ttk.Button(frm, text="選択", command=self._pick_source)
        self._btn_pick.grid(row=0, column=2, **pad)

        ttk.Label(frm, text="照合値 (任意, 64文字):").grid(row=1, column=0, sticky="w", **pad)
        self._exp_entry = ttk.Entry(frm, textvariable=self.expected)
        self._exp_entry.grid(row=1, column=1, sticky="ew", **pad)

        ttk.Label(frm, text="BLAKE3 ハッシュ:").grid(row=2, column=0, sticky="w", **pad)
        self._dig_entry = ttk.Entry(frm, textvariable=self.digest, state="readonly", width=70)
        self._dig_entry.grid(row=2, column=1, columnspan=2, sticky="ew", **pad)

        self._status_lbl = ttk.Label(frm, textvariable=self.status, foreground="#006600")
        self._status_lbl.grid(row=3, column=1, sticky="w", **pad)

        btns = ttk.Frame(frm)
        btns.grid(row=4, column=1, sticky="w", **pad)
        self._btn_start = ttk.Button(btns, text="計算", command=self.start_hash)
        self._btn_start.pack(side="left", padx=4)
        self._btn_stop = ttk.Button(btns, text="停止", command=self.stop_hash, state="disabled")
        self._btn_stop.pack(side="left", padx=4)
        self._btn_copy = ttk.Button(btns, text="コピー", command=self.copy_hash, state="disabled")
        self._btn_copy.pack(side="left", padx=4)

        notice = ("BLAKE3専用です。SHA-256とは比較できません。\n"
                  "ハッシュ一致は配布元や安全性を保証しません。")
        ttk.Label(frm, text=notice, foreground="#555555").grid(row=5, column=1, sticky="w", pady=(10, 0))

        frm.columnconfigure(1, weight=1)

    def _pick_source(self):
        if self.running:
            return
        path = filedialog.askopenfilename(title="対象ファイルを選択")
        if path:
            self.source.set(path)
            self._on_input_change()

    def _on_input_change(self):
        if not self.running:
            self.digest.set("")
            self.status.set("待機中")
            self._status_lbl.config(foreground='#333333')
            self._btn_copy.config(state="disabled")

    def start_hash(self):
        if self.running:
            return
        src = self.source.get().strip()
        exp_raw = self.expected.get().strip()
        if not src:
            self.status.set("対象ファイルが未選択です。")
            return
        try:
            exp = normalize_expected(exp_raw)
        except ValueError as e:
            self.status.set(str(e))
            return
        if not Path(src).is_file():
            self.status.set("対象ファイルが存在しません。")
            return

        self.running = True
        self._cancel.clear()
        self.digest.set("")
        self.status.set("計算中...")
        self._set_running_ui(True)

        self._worker_thread = threading.Thread(
            target=self._run_worker, args=(Path(src), exp), daemon=True
        )
        self._worker_thread.start()

    def _run_worker(self, src: Path, exp: str):
        try:
            exe = resource_dir() / "b3sum.exe"
            digest = hash_file(exe, src, self._cancel)
            if exp:
                if digest == exp:
                    msg = "一致"
                else:
                    msg = "不一致"
            else:
                msg = "計算完了"
            self._q.put(("ok", digest, msg))
        except InterruptedError:
            self._q.put(("stop", None, "停止しました。"))
        except TimeoutError:
            self._q.put(("err", None, "タイムアウトしました。"))
        except ValueError as e:
            self._q.put(("err", None, str(e)))
        except Exception:
            self._q.put(("err", None, "計算に失敗しました。ファイルへのアクセス権を確認してください。"))

    def _poll_queue(self):
        try:
            while True:
                kind, digest, msg = self._q.get_nowait()
                self._handle_result(kind, digest, msg)
        except queue.Empty:
            pass
        self.after(100, self._poll_queue)

    def _handle_result(self, kind, digest, msg):
        self.running = False
        self._status_lbl.config(foreground='#b42318' if kind=='err' or msg=='不一致' else '#006600')
        self._set_running_ui(False)
        if kind == "ok":
            self.digest.set(digest)
            self.status.set(msg)
            self._btn_copy.config(state="normal")
        elif kind == "stop":
            self.status.set(msg)
        else:
            self.status.set(msg)

    def _set_running_ui(self, on: bool):
        state = "disabled" if on else "normal"
        self._src_entry.config(state=state)
        self._btn_pick.config(state=state)
        self._exp_entry.config(state=state)
        self._btn_start.config(state=state)
        self._btn_stop.config(state="normal" if on else "disabled")
        if on:
            self._btn_copy.config(state="disabled")
        elif self.digest.get():
            self._btn_copy.config(state="normal")

    def stop_hash(self):
        if self.running:
            self._cancel.set()
            self.status.set("停止中...")

    def copy_hash(self):
        if self.running:
            return
        d = self.digest.get()
        if d:
            self.clipboard_clear()
            self.clipboard_append(d)

    def close(self):
        if self.running:
            self._cancel.set()
            if self._worker_thread and self._worker_thread.is_alive():
                self._worker_thread.join(timeout=2.0)
        self.destroy()


if __name__=='__main__':
    App().mainloop()
