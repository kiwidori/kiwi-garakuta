"""Kiwi PNG: a GUI for lossless PNG optimization."""
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
from core import optimize,resource_dir

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("きういPNG圧縮")
        self.geometry("900x420")
        self.minsize(760, 360)

        self.source = tk.StringVar()
        self.destination = tk.StringVar()
        self.level = tk.IntVar(value=2)
        self.status = tk.StringVar(value="準備完了")
        self.result = tk.StringVar(value="")
        self.running = False

        self._q = queue.Queue()
        self._cancel = threading.Event()
        self._worker = None

        self._build_ui()
        self.protocol("WM_DELETE_WINDOW", self.close)
        self.after(100, self._poll_queue)
        # Additional upstream operations run in a separate structured window.
        self.advanced = attach(self, source_dir=Path(__file__).resolve().parent)

    def _build_ui(self):
        pad = {"padx": 8, "pady": 4}
        frm = ttk.Frame(self)
        frm.pack(fill="both", expand=True, padx=10, pady=10)

        ttk.Label(frm, text="元画像 (PNG)").grid(row=0, column=0, sticky="w", **pad)
        ttk.Entry(frm, textvariable=self.source, width=60).grid(row=0, column=1, sticky="ew", **pad)
        ttk.Button(frm, text="選択…", command=self._pick_source).grid(row=0, column=2, **pad)

        ttk.Label(frm, text="保存先 (PNG)").grid(row=1, column=0, sticky="w", **pad)
        ttk.Entry(frm, textvariable=self.destination, width=60).grid(row=1, column=1, sticky="ew", **pad)
        ttk.Button(frm, text="保存先…", command=self._pick_destination).grid(row=1, column=2, **pad)

        ttk.Label(frm, text="圧縮レベル (0-4)").grid(row=2, column=0, sticky="w", **pad)
        cb = ttk.Combobox(frm, textvariable=self.level, values=["0", "1", "2", "3", "4"], state="readonly", width=5)
        cb.grid(row=2, column=1, sticky="w", **pad)

        btns = ttk.Frame(frm)
        btns.grid(row=3, column=0, columnspan=3, sticky="w", **pad)
        self.btn_start = ttk.Button(btns, text="圧縮", command=self.start_optimize)
        self.btn_start.pack(side="left", padx=4)
        self.btn_stop = ttk.Button(btns, text="停止", command=self.stop_optimize, state="disabled")
        self.btn_stop.pack(side="left", padx=4)

        ttk.Label(frm, textvariable=self.status).grid(row=4, column=0, columnspan=3, sticky="w", **pad)

        notice = "元画像を残して別ファイルへ保存します。容量が小さくならない場合もあります。"
        ttk.Label(frm, text=notice, foreground="#555").grid(row=5, column=0, columnspan=3, sticky="w", **pad)

        res_frm = ttk.LabelFrame(frm, text="結果")
        res_frm.grid(row=6, column=0, columnspan=3, sticky="nsew", **pad)
        frm.rowconfigure(6, weight=1)
        frm.columnconfigure(1, weight=1)
        ttk.Label(res_frm, textvariable=self.result, wraplength=800, justify="left").pack(fill="both", expand=True, padx=6, pady=6)

    def _pick_source(self):
        p = filedialog.askopenfilename(filetypes=[("PNG", "*.png")])
        if p:
            self.source.set(p)
            stem = Path(p).stem
            self.destination.set(str(Path(p).parent / f"{stem}-optimized.png"))

    def _pick_destination(self):
        default = self.destination.get()
        if not default:
            src = self.source.get()
            if src:
                default = str(Path(src).parent / f"{Path(src).stem}-optimized.png")
        target = Path(default) if default else None
        p = filedialog.asksaveasfilename(defaultextension=".png", filetypes=[("PNG", "*.png")], initialdir=str(target.parent) if target else None, initialfile=target.name if target else None)
        if p:
            self.destination.set(p)

    def start_optimize(self):
        if self.running:
            return
        src = self.source.get()
        dst = self.destination.get()
        lvl = self.level.get()
        if not src or not dst:
            self.status.set("元画像と保存先を指定してください。")
            return
        if Path(dst).exists():
            self.status.set("保存先は既存ファイルに上書きできません。")
            return
        self.running = True
        self.btn_start.config(state="disabled")
        self.btn_stop.config(state="normal")
        self.status.set("最適化中…")
        self.result.set("")
        self._cancel.clear()
        self._worker = threading.Thread(target=self._worker_run, args=(src, dst, lvl), daemon=True)
        self._worker.start()

    def stop_optimize(self):
        if self.running:
            self._cancel.set()
            self.status.set("停止要求中…")

    def _worker_run(self, src, dst, lvl):
        try:
            exe = resource_dir() / "oxipng.exe"
            res = optimize(exe, Path(src), Path(dst), lvl, self._cancel)
            self._q.put(("ok", res))
        except ValueError as e:
            self._q.put(("err", str(e)))
        except InterruptedError:
            self._q.put(("stop", None))
        except TimeoutError:
            self._q.put(("timeout", None))
        except Exception:
            self._q.put(("err", "予期しないエラーが発生しました。"))

    def _poll_queue(self):
        try:
            while True:
                kind, payload = self._q.get_nowait()
                self._handle_msg(kind, payload)
        except queue.Empty:
            pass
        self.after(100, self._poll_queue)

    def _handle_msg(self, kind, payload):
        self.running = False
        self.btn_start.config(state="normal")
        self.btn_stop.config(state="disabled")
        if kind == "ok":
            b = payload.get("before", 0)
            a = payload.get("after", 0)
            sp = payload.get("saved_percent", 0.0)
            self.status.set("完了")
            self.result.set(f"元: {b:,} バイト\n新: {a:,} バイト\n削減率: {sp:.2f}%")
        elif kind == "stop":
            self.status.set("停止しました。")
            self.result.set("処理が停止されました。出力ファイルは作成されませんでした。")
        elif kind == "timeout":
            self.status.set("タイムアウト")
            self.result.set("120秒を超えたため処理を中断しました。")
        else:
            self.status.set("エラー")
            self.result.set(payload or "エラーが発生しました。")

    def close(self):
        if self.running:
            self._cancel.set()
            if self._worker:
                self._worker.join(timeout=2.0)
        self.destroy()


if __name__=='__main__':
    App().mainloop()
