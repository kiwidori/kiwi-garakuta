"""Offline Windows GUI for ascii-image-converter."""
import os
import queue
import threading
import tkinter as tk
from tkinter import ttk, filedialog
from pathlib import Path

from core import convert_image, resource_dir
APP_TITLE = "きうい文字絵"
WINDOW_SIZE = "1000x720"
POLL_INTERVAL_MS = 100


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.root = self
        self.root.title(APP_TITLE)
        self.root.geometry(WINDOW_SIZE)
        self.root.minsize(760, 550)
        self.path = tk.StringVar()
        self.filename = tk.StringVar()
        self.width = tk.StringVar(value="80")
        self.negative = tk.BooleanVar(value=False)
        self.braille = tk.BooleanVar(value=False)
        self.status = tk.StringVar(value="待機中")
        self.running = False
        self.worker_thread = None
        self.result_queue = queue.Queue()
        self.cancel_event = threading.Event()

        self._setup_ui()
        self._bind_events()
        self._poll_queue()

    def _setup_ui(self):
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.pack(fill=tk.BOTH, expand=True)
        input_frame = ttk.LabelFrame(main_frame, text="入力画像・設定", padding="10")
        input_frame.pack(fill=tk.X, pady=(0, 10))
        path_row = ttk.Frame(input_frame)
        path_row.pack(fill=tk.X, pady=(0, 5))

        self.path_entry = ttk.Entry(path_row, textvariable=self.filename, state="readonly")
        self.path_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 5))

        self.browse_btn = ttk.Button(path_row, text="画像を選ぶ", command=self._browse_file)
        self.browse_btn.pack(side=tk.RIGHT)
        options_row = ttk.Frame(input_frame)
        options_row.pack(fill=tk.X)

        ttk.Label(options_row, text="横幅（20〜160文字）:").pack(side=tk.LEFT)
        self.width_entry = ttk.Entry(options_row, textvariable=self.width, width=5)
        self.width_entry.pack(side=tk.LEFT, padx=(5, 15))

        self.negative_check = ttk.Checkbutton(options_row, text="白黒反転", variable=self.negative)
        self.negative_check.pack(side=tk.LEFT, padx=(0, 15))

        self.braille_check = ttk.Checkbutton(options_row, text="点字文字", variable=self.braille)
        self.braille_check.pack(side=tk.LEFT)
        control_frame = ttk.Frame(main_frame)
        control_frame.pack(fill=tk.X, pady=(0, 10))

        self.convert_btn = ttk.Button(control_frame, text="変換", command=self.start_convert)
        self.convert_btn.pack(side=tk.LEFT, padx=(0, 5))

        self.stop_btn = ttk.Button(control_frame, text="停止", command=self.stop_convert, state="disabled")
        self.stop_btn.pack(side=tk.LEFT)
        output_frame = ttk.LabelFrame(main_frame, text="文字絵（等幅フォント）", padding="5")
        output_frame.pack(fill=tk.BOTH, expand=True)
        self.output = tk.Text(output_frame, wrap="none", font=("Consolas", 10), bg="#17212b", fg="#f5f7fa", state="disabled")
        scrollbar_y = ttk.Scrollbar(output_frame, orient="vertical", command=self.output.yview)
        scrollbar_x = ttk.Scrollbar(output_frame, orient="horizontal", command=self.output.xview)

        self.output.configure(yscrollcommand=scrollbar_y.set, xscrollcommand=scrollbar_x.set)

        self.output.grid(row=0, column=0, sticky="nsew")
        scrollbar_y.grid(row=0, column=1, sticky="ns")
        scrollbar_x.grid(row=1, column=0, sticky="ew")

        output_frame.grid_rowconfigure(0, weight=1)
        output_frame.grid_columnconfigure(0, weight=1)
        action_frame = ttk.Frame(main_frame)
        action_frame.pack(fill=tk.X, pady=(5, 0))

        self.copy_btn = ttk.Button(action_frame, text="コピー", command=self.copy_output, state="disabled")
        self.copy_btn.pack(side=tk.LEFT, padx=(0, 5))

        self.save_btn = ttk.Button(action_frame, text="テキスト保存", command=self.save_output, state="disabled")
        self.save_btn.pack(side=tk.LEFT)
        status_bar = ttk.Label(self.root, textvariable=self.status, relief="sunken", anchor="w", padding="5")
        status_bar.pack(fill=tk.X, side=tk.BOTTOM)

    def _bind_events(self):
        self.root.protocol("WM_DELETE_WINDOW", self.close)
        self.path.trace_add("write", self._on_input_change)
        self.width.trace_add("write", self._on_input_change)
        self.negative.trace_add("write", self._on_input_change)
        self.braille.trace_add("write", self._on_input_change)

    def _on_input_change(self, *args):
        self.filename.set(Path(self.path.get()).name)
        if not self.running:
            self._clear_output()
            self.status.set("待機中")

    def _browse_file(self):
        if self.running:
            return
        filename = filedialog.askopenfilename(parent=self, title="静止画像を選択", filetypes=[("画像", "*.png *.jpg *.jpeg *.bmp *.webp *.tiff *.tif")])
        if filename:
            self.path.set(filename)

    def _clear_output(self):
        self.output.config(state="normal")
        self.output.delete("1.0", tk.END)
        self.output.config(state="disabled")
        self.copy_btn.config(state="disabled")
        self.save_btn.config(state="disabled")

    def _set_buttons_state(self, running: bool):
        if running:
            self.browse_btn.config(state="disabled")
            self.convert_btn.config(state="disabled")
            self.negative_check.config(state="disabled")
            self.braille_check.config(state="disabled")
            self.width_entry.config(state="disabled")
            self.stop_btn.config(state="normal")
        else:
            self.browse_btn.config(state="normal")
            self.convert_btn.config(state="normal")
            self.negative_check.config(state="normal")
            self.braille_check.config(state="normal")
            self.width_entry.config(state="normal")
            self.stop_btn.config(state="disabled")

    def start_convert(self):
        if self.running:
            return
        self._clear_output()
        if not self.path.get():
            self.status.set("画像を選んでください。")
            return
        try:
            width = int(self.width.get())
            if not 20 <= width <= 160:
                raise ValueError()
        except ValueError:
            self.status.set("横幅は20〜160文字で指定してください。")
            return
        self.running = True
        self.cancel_event.clear()
        self._set_buttons_state(True)
        self.status.set("変換中...")
        self.worker_thread = threading.Thread(target=self._worker, args=(Path(self.path.get()), width, self.negative.get(), self.braille.get()), daemon=True)
        self.worker_thread.start()

    def stop_convert(self):
        if self.running:
            self.cancel_event.set()
            self.status.set("停止中...")

    def _worker(self, path, width, negative, braille):
        try:
            result = convert_image(resource_dir()/"ascii-image-converter.exe", path, width, negative, braille, self.cancel_event)
            self.result_queue.put(("success", result))
        except InterruptedError:
            self.result_queue.put(("cancelled", ""))
        except TimeoutError:
            self.result_queue.put(("error", "30秒以内に変換できませんでした。"))
        except ValueError as exc:
            self.result_queue.put(("error", str(exc)))
        except Exception:
            self.result_queue.put(("error", "変換できませんでした。画像やアクセス権を確認してください。"))

    def _poll_queue(self):
        try:
            while True:
                status, data = self.result_queue.get_nowait()
                self._handle_result(status, data)
        except queue.Empty:
            pass
        self.root.after(POLL_INTERVAL_MS, self._poll_queue)

    def _handle_result(self, status, data):
        self.running = False
        self._set_buttons_state(False)

        if status == "success":
            self.status.set("変換完了")
            self.output.config(state="normal")
            self.output.delete("1.0", tk.END)
            self.output.insert("1.0", data)
            self.output.config(state="disabled")
            self.copy_btn.config(state="normal")
            self.save_btn.config(state="normal")
        elif status == "cancelled":
            self.status.set("停止しました")
            self._clear_output()
        else:  # error
            self.status.set(data)
            self._clear_output()

    def copy_output(self):
        content = self.output.get("1.0", "end-1c")
        if not self.running and content:
            self.clipboard_clear()
            self.clipboard_append(content)
            self.status.set("コピーしました")

    def save_output(self):
        content = self.output.get("1.0", "end-1c")
        if self.running or not content:
            return
        filename = filedialog.asksaveasfilename(parent=self, title="文字絵を保存", defaultextension=".txt", filetypes=[("テキスト", "*.txt")], initialfile="ascii_output.txt", confirmoverwrite=True)
        if not filename:
            return
        try:
            destination = Path(filename)
            source = Path(self.path.get())
            if destination.resolve() == source.resolve() or (destination.exists() and source.exists() and os.path.samefile(destination, source)):
                self.status.set("入力画像と同じファイルには保存できません。")
                return
            with destination.open('w', encoding='utf-8', newline='\n') as stream:
                stream.write(content)
            self.status.set("テキストを保存しました")
        except OSError:
            self.status.set("保存できませんでした。保存先やアクセス権を確認してください。")

    def close(self):
        self.cancel_event.set()
        if self.worker_thread and self.worker_thread.is_alive():
            self.worker_thread.join(timeout=2)
        self.destroy()


if __name__ == "__main__":
    App().mainloop()
