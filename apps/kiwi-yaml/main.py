"""Kiwi YAML: fixed-expression YAML formatting and conversion."""
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
from core import convert,resource_dir,save_result

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("きういYAML")
        self.geometry("980x620")
        self.minsize(760, 460)
        self.protocol("WM_DELETE_WINDOW", self.close)

        self.source = tk.StringVar()
        self.mode = tk.StringVar(value="YAML整形")
        self.status = tk.StringVar(value="待機中")
        self.running = False
        self.result_text = ""
        self._worker_thread = None
        self._result_source = None
        self._result_mode = None
        self._q = queue.Queue()
        self._cancel = threading.Event()

        frm = ttk.Frame(self, padding=10)
        frm.pack(fill="both", expand=True)

        row1 = ttk.Frame(frm)
        row1.pack(fill="x", pady=(0, 8))
        ttk.Label(row1, text="ソースファイル:").pack(side="left")
        self.src_entry = ttk.Entry(row1, textvariable=self.source, state="readonly")
        self.src_entry.pack(side="left", fill="x", expand=True, padx=5)
        self.btn_browse = ttk.Button(row1, text="参照...", command=self._pick_source)
        self.btn_browse.pack(side="left")

        row2 = ttk.Frame(frm)
        row2.pack(fill="x", pady=(0, 8))
        ttk.Label(row2, text="モード:").pack(side="left")
        self.mode_box = ttk.Combobox(row2, textvariable=self.mode, state="readonly",
                                     values=["YAML整形", "JSON変換"], width=15)
        self.mode_box.pack(side="left", padx=5)
        self.mode_box.bind("<<ComboboxSelected>>", lambda e: self._on_idle_change())

        self.source.trace_add('write', lambda *args: self._on_idle_change())
        self.mode.trace_add('write', lambda *args: self._on_idle_change())

        notice = ("JSON変換ではコメント・タグなどが失われる場合があります。"
                  "複数文書は複数のJSON値になります。")
        ttk.Label(frm, text=notice, foreground="#555").pack(anchor="w", pady=(0, 4))

        btns = ttk.Frame(frm)
        btns.pack(fill="x", pady=(0, 8))
        self.btn_run = ttk.Button(btns, text="実行", command=self.start_convert)
        self.btn_run.pack(side="left", padx=(0, 5))
        self.btn_stop = ttk.Button(btns, text="停止", command=self.stop_convert, state="disabled")
        self.btn_stop.pack(side="left", padx=(0, 5))
        self.btn_save = ttk.Button(btns, text="保存", command=self._save_dialog, state="disabled")
        self.btn_save.pack(side="left")

        out_frm = ttk.Frame(frm)
        out_frm.pack(fill="both", expand=True)
        self.output = tk.Text(out_frm, wrap="none", state="disabled")
        sb_y = ttk.Scrollbar(out_frm, orient="vertical", command=self.output.yview)
        sb_x = ttk.Scrollbar(out_frm, orient="horizontal", command=self.output.xview)
        self.output.configure(yscrollcommand=sb_y.set, xscrollcommand=sb_x.set)
        self.output.grid(row=0, column=0, sticky="nsew")
        sb_y.grid(row=0, column=1, sticky="ns")
        sb_x.grid(row=1, column=0, sticky="ew")
        out_frm.grid_rowconfigure(0, weight=1)
        out_frm.grid_columnconfigure(0, weight=1)

        ttk.Label(frm, textvariable=self.status).pack(anchor="w", pady=(8, 0))

        self.after(100, self._poll_queue)
        # Additional upstream operations run in a separate structured window.
        self.advanced = attach(self, source_dir=Path(__file__).resolve().parent)

    def _pick_source(self):
        p = filedialog.askopenfilename(
            title="YAMLファイルを選択",
            filetypes=[("YAMLファイル", "*.yaml *.yml"), ("すべてのファイル", "*.*")])
        if p:
            self.source.set(p)
            self._on_idle_change()

    def _on_idle_change(self):
        if not self.running:
            self._clear_output()

    def _clear_output(self):
        self.output.configure(state="normal")
        self.output.delete("1.0", "end")
        self.output.configure(state="disabled")
        self.result_text = ""
        self.btn_save.configure(state="disabled")

    def start_convert(self):
        if self.running:
            return
        src = Path(self.source.get())
        if not src.is_file():
            self.status.set("ソースファイルが選択されていません。")
            return
        mode = "json" if self.mode.get() == "JSON変換" else "yaml"
        self.running = True
        self.status.set("変換中...")
        self._clear_output()
        self.btn_run.configure(state="disabled")
        self.btn_stop.configure(state="normal")
        self.btn_save.configure(state="disabled")
        self.src_entry.configure(state="disabled")
        self.btn_browse.configure(state="disabled")
        self.mode_box.configure(state="disabled")
        self._cancel.clear()
        self._result_source = src.resolve()
        self._result_mode = mode
        self._worker_thread = threading.Thread(target=self._worker, args=(src, mode), daemon=True)
        self._worker_thread.start()

    def _worker(self, src: Path, mode: str):
        try:
            text = convert(resource_dir() / "yq.exe", src, mode, self._cancel)
            self._q.put(("ok", text))
        except InterruptedError:
            self._q.put(("err", "処理を停止しました。"))
        except TimeoutError:
            self._q.put(("err", "15秒を超えたため停止しました。"))
        except ValueError as e:
            self._q.put(("err", str(e)))
        except Exception:
            self._q.put(("err", "予期しないエラーが発生しました。"))

    def _poll_queue(self):
        try:
            while True:
                kind, payload = self._q.get_nowait()
                if kind == "ok":
                    self.result_text = payload
                    preview = payload[:120000]
                    if len(payload) > 120000:
                        preview += "\n... (表示が切り詰められています)"
                    self.output.configure(state="normal")
                    self.output.delete("1.0", "end")
                    self.output.insert("1.0", preview)
                    self.output.configure(state="disabled")
                    self.status.set("完了")
                    self.btn_save.configure(state="normal")
                else:
                    self.status.set(payload)
                self._finish_ui()
        except queue.Empty:
            pass
        self.after(100, self._poll_queue)

    def _finish_ui(self):
        self.running = False
        self.btn_run.configure(state="normal")
        self.btn_stop.configure(state="disabled")
        self.src_entry.configure(state="readonly")
        self.btn_browse.configure(state="normal")
        self.mode_box.configure(state="readonly")

    def stop_convert(self):
        if self.running:
            self._cancel.set()
            self.status.set("停止要求中...")

    def save_to(self, path: Path):
        if self.running or not self.result_text or self._result_source is None:
            raise ValueError("保存する結果がありません。")
        save_result(self.result_text, self._result_source, path)

    def _save_dialog(self):
        if self.running or not self.result_text:
            return
        p = filedialog.asksaveasfilename(
            title="結果を保存",
            defaultextension=".json" if self._result_mode == 'json' else '.yaml',
            filetypes=[("結果ファイル", "*.json *.yaml *.yml *.txt"), ("すべてのファイル", "*.*")])
        if not p:
            return
        try:
            self.save_to(Path(p))
            self.status.set("保存しました。")
        except ValueError as error:
            self.status.set(str(error))
        except OSError:
            self.status.set("保存に失敗しました。")

    def close(self):
        self._cancel.set()
        if self._worker_thread and self._worker_thread.is_alive():
            self._worker_thread.join(timeout=2)
        self.destroy()


if __name__=='__main__':
    App().mainloop()
