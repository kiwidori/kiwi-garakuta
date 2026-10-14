import queue, threading, json, tkinter.ttk as ttk
from pathlib import Path
import runtime,system_core,space_core

class PcMixin:
    def build_pc_panel(self):
        self.pc_frame = ttk.LabelFrame(self, text='PCの概要')
        self.pc_frame.pack(before=self.pack_slaves()[0], fill="x", padx=5, pady=(5, 0))
        btns = ttk.Frame(self.pc_frame); btns.pack(fill="x", pady=(5, 0))
        ttk.Button(btns, text='PC・ドライブ更新', command=self.refresh_pc).pack(side="left")
        ttk.Button(btns, text='概要をコピー', command=self.copy_pc).pack(side="left", padx=5)
        table = ttk.Frame(self.pc_frame); table.pack(fill="x")
        cols = ("key", "value")
        self.info_tree = ttk.Treeview(table, columns=cols, show="headings", height=4)
        self.info_tree.heading("key", text="項目"); self.info_tree.heading("value", text="値")
        self.info_tree.column("key", width=120); self.info_tree.column("value", width=350)
        vsb = ttk.Scrollbar(table, orient="vertical", command=self.info_tree.yview)
        self.info_tree.configure(yscrollcommand=vsb.set)
        self.info_tree.pack(side="left", fill="both", expand=True); vsb.pack(side="right", fill="y")
        self.after(80, self._poll_pc)

    def refresh_pc(self):
        if self.busy() or self.pc_busy:
            return
        self.pc_busy = True
        self.pc_cancel.clear()
        self.stop_button.config(state="normal")
        self.status.set("PC情報を取得中...")
        self.pc_thread = threading.Thread(target=self._pc_worker, daemon=True)
        self.pc_thread.start()

    def _pc_worker(self):
        try:
            ff = self.native_paths["fastfetch"]
            r1 = runtime.execute(ff, ["--config", "none", "--format", "json", "--structure", "OS:CPU:GPU:Memory:Display"], cancel_event=self.pc_cancel, timeout=15, max_output=1000000)
            if self.pc_cancel.is_set(): raise InterruptedError()
            if r1["returncode"] != 0: raise ValueError("PC情報の取得に失敗しました")
            rows = system_core.summarize(json.loads(r1["stdout"].decode('utf-8-sig')))
            duf = self.native_paths["duf"]
            r2 = runtime.execute(duf, ["--json", "--only", "local"], cancel_event=self.pc_cancel, timeout=15, max_output=1000000)
            if self.pc_cancel.is_set(): raise InterruptedError()
            if r2["returncode"] != 0: raise ValueError("ドライブ情報の取得に失敗しました")
            drives = space_core.parse_drives(r2["stdout"])
            self.pc_results.put(("ok", rows, drives))
        except InterruptedError:
            self.pc_results.put(("error", "処理を停止しました"))
        except (ValueError, json.JSONDecodeError):
            self.pc_results.put(("error", "情報の取得または解析に失敗しました"))
        except Exception:
            self.pc_results.put(("error", "予期しないエラーが発生しました"))

    def _poll_pc(self):
        if getattr(self, "_closing", False):
            return
        try:
            while True:
                msg = self.pc_results.get_nowait()
                if msg[0] == "ok":
                    rows, drives = msg[1], msg[2]
                    self.pc_rows = rows
                    for i in self.info_tree.get_children():
                        self.info_tree.delete(i)
                    for k, v in rows:
                        self.info_tree.insert("", "end", values=(k, v))
                    self.drives_snapshot = drives
                    self._update_drive_table()
                    self.status.set("PC・ドライブ情報を更新しました。")
                else:
                    self.status.set(msg[1])
                self.pc_busy = False
                self.stop_button.config(state="disabled")
        except queue.Empty:
            pass
        if not getattr(self, "_closing", False):
            self.after(80, self._poll_pc)

    def copy_pc(self):
        if self.busy() or not self.pc_rows:
            return
        lines = [f"{k}: {v}" for k, v in self.pc_rows]
        if hasattr(self, "drives_snapshot"):
            for d in self.drives_snapshot:
                lines.append(f"ドライブ {d['drive']}: 総量 {space_core.format_size(d['total'])} / 空き {space_core.format_size(d['free'])}")
        self.clipboard_clear()
        self.clipboard_append("\n".join(lines))
        self.status.set("PC概要をコピーしました")
