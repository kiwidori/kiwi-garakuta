"""Kiwi Color: opaque HEX, RGB and HSL conversion."""
import tkinter as tk
from tkinter import ttk,colorchooser
import threading
import queue
from pathlib import Path
from core import convert_color,resource_dir,validate_input

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("きうい色変換")
        self.geometry("900x420")
        self.minsize(760, 400)

        self.color = tk.StringVar(value="#66bb44")
        self.hex_value = tk.StringVar()
        self.rgb_value = tk.StringVar()
        self.hsl_value = tk.StringVar()
        self.status = tk.StringVar(value="待機中")
        self.running = False

        self._worker_thread = None
        self._cancel_event = threading.Event()
        self._result_queue = queue.Queue()

        self._build_ui()
        self.color.trace_add("write", self._on_input_change)
        self._poll_queue()
        self.protocol("WM_DELETE_WINDOW", self.close)

    def _build_ui(self):
        main_frame = ttk.Frame(self, padding=10)
        main_frame.pack(fill="both", expand=True)

        ttk.Label(main_frame, text="不透明な色のHEX・RGB・HSLを変換します。数値の丸めで表記が変わる場合があります。").pack(anchor="w", pady=(0, 10))

        input_frame = ttk.Frame(main_frame)
        input_frame.pack(fill="x", pady=5)
        self.input_entry = ttk.Entry(input_frame, textvariable=self.color, width=30)
        self.input_entry.pack(side="left", fill="x", expand=True)

        btn_frame = ttk.Frame(input_frame)
        btn_frame.pack(side="left", padx=5)
        self.convert_btn = ttk.Button(btn_frame, text="変換", command=self.start_convert)
        self.convert_btn.pack(side="left")
        self.stop_btn = ttk.Button(btn_frame, text="停止", command=self.stop_convert, state="disabled")
        self.stop_btn.pack(side="left", padx=5)
        self.pick_btn = ttk.Button(btn_frame, text="色を選ぶ", command=self._pick_color)
        self.pick_btn.pack(side="left", padx=5)

        results_frame = ttk.LabelFrame(main_frame, text="結果", padding=10)
        results_frame.pack(fill="both", expand=True, pady=10)

        self.preview = tk.Canvas(results_frame, width=200, height=100, bg="#eeeeee", highlightthickness=0)
        self.preview.pack(side="left", padx=10, pady=10)

        res_grid = ttk.Frame(results_frame)
        res_grid.pack(side="left", fill="both", expand=True)

        self.copy_buttons = {}
        for row, (fmt, variable) in enumerate((("hex", self.hex_value), ("rgb", self.rgb_value), ("hsl", self.hsl_value))):
            ttk.Label(res_grid, text=fmt.upper()).grid(row=row, column=0, padx=(0, 8), sticky="w")
            entry = ttk.Entry(res_grid, textvariable=variable, state="readonly")
            entry.grid(row=row, column=1, sticky="ew", pady=2)
            button = ttk.Button(res_grid, text="コピー", state="disabled", command=lambda f=fmt: self.copy_value(f))
            button.grid(row=row, column=2, padx=5)
            self.copy_buttons[fmt] = button
        res_grid.columnconfigure(1, weight=1)

        ttk.Label(main_frame, textvariable=self.status).pack(anchor="w", pady=5)

    def _on_input_change(self, *args):
        if not self.running:
            self._clear_outputs()

    def _clear_outputs(self):
        self.hex_value.set("")
        self.rgb_value.set("")
        self.hsl_value.set("")
        self.preview.config(bg="#eeeeee")
        for button in self.copy_buttons.values():
            button.config(state="disabled")
        self.status.set("待機中")

    def _pick_color(self):
        if self.running:
            return
        color = colorchooser.askcolor(parent=self, initialcolor=self.hex_value.get() or "#66bb44")
        if color and color[1]:
            self.color.set(color[1])

    def start_convert(self):
        if self.running:
            return
        value = self.color.get().strip()
        try:
            safe_value = validate_input(value)
        except ValueError as e:
            self.status.set(str(e))
            return

        self.running = True
        self.convert_btn.config(state="disabled")
        self.stop_btn.config(state="normal")
        self.input_entry.config(state="disabled")
        self.pick_btn.config(state="disabled")
        self._clear_outputs()
        self.status.set("変換中...")
        self._cancel_event.clear()

        self._worker_thread = threading.Thread(target=self._worker, args=(safe_value,), daemon=True)
        self._worker_thread.start()

    def stop_convert(self):
        if self.running:
            self._cancel_event.set()
            self.status.set("停止中...")

    def _worker(self, value):
        try:
            result = convert_color(resource_dir() / "pastel.exe", value, self._cancel_event)
            self._result_queue.put(("success", result))
        except InterruptedError:
            self._result_queue.put(("interrupted", None))
        except TimeoutError:
            self._result_queue.put(("timeout", None))
        except ValueError as exc:
            self._result_queue.put(("error", str(exc)))
        except Exception:
            self._result_queue.put(("error", None))

    def _poll_queue(self):
        try:
            while True:
                msg_type, data = self._result_queue.get_nowait()
                self._handle_result(msg_type, data)
        except queue.Empty:
            pass
        self.after(100, self._poll_queue)

    def _handle_result(self, msg_type, data):
        self.running = False
        self.convert_btn.config(state="normal")
        self.stop_btn.config(state="disabled")
        self.input_entry.config(state="normal")
        self.pick_btn.config(state="normal")

        if msg_type == "success":
            self.hex_value.set(data.get("hex", ""))
            self.rgb_value.set(data.get("rgb", ""))
            self.hsl_value.set(data.get("hsl", ""))
            hex_val = data.get("hex", "")
            if hex_val:
                self.preview.config(bg=hex_val)
            self.status.set("変換完了")
            for button in self.copy_buttons.values():
                button.config(state="normal")
        elif msg_type == "interrupted":
            self.status.set("停止しました")
        elif msg_type == "timeout":
            self.status.set("15秒以内に変換できませんでした")
        else:
            self.status.set(data or "変換に失敗しました")

    def copy_value(self, fmt):
        values = {"hex": self.hex_value, "rgb": self.rgb_value, "hsl": self.hsl_value}
        if self.running or fmt not in values or not values[fmt].get():
            return
        self.clipboard_clear()
        self.clipboard_append(values[fmt].get())

    def close(self):
        if self.running:
            self._cancel_event.set()
            if self._worker_thread:
                self._worker_thread.join(timeout=2)
        self.destroy()


if __name__=='__main__':
    App().mainloop()
