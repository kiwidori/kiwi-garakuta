# advanced.py
"""
Reusable advanced-functions window for Windows GUI wrappers.
"""
import sys
import os
import json
import re
import subprocess
import tempfile
import threading
import queue
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple

from runtime import build_command, execute, resource_path, _strip_ansi

BUNDLED_TOOLS = {
    'gron.exe': 'gron.exe',
    'actionlint.exe': 'actionlint.exe',
    'yamlfmt.exe': 'yamlfmt.exe',
    'ascii-image-converter.exe': 'ascii-image-converter.exe',
    'hexyl.exe': 'hexyl.exe', 'numbat.exe': 'numbat.exe',
    'bat.exe': 'bat.exe', 'pastel.exe': 'pastel.exe', 'scc.exe': 'scc.exe',
    'dasel.exe': 'dasel.exe', 'difft.exe': 'difft.exe', 'dust.exe': 'dust.exe',
    'fd.exe': 'fd.exe', 'b3sum.exe': 'b3sum.exe', 'xh.exe': 'xh.exe',
    'jq.exe': 'jq.exe', 'glow.exe': 'glow.exe', 'minify.exe': 'minify.exe',
    'oxipng.exe': 'oxipng.exe', 'code2prompt.exe': 'code2prompt.exe',
    'grex.exe': 'grex.exe', 'sd.exe': 'sd.exe', 'rg.exe': 'rg.exe',
    'gitleaks.exe': 'gitleaks.exe', 'shfmt.exe': 'shfmt.exe',
    'duf.exe': 'duf.exe', 'fastfetch.exe': 'fastfetch.exe', 'yq.exe': 'yq.exe',
}

class AdvancedController:
    def __init__(self, app: tk.Tk, tool_name: str, help_file_name: str, spec: Dict[str, Any], source_dir: Optional[Path] = None):
        self.app = app
        self.tool_name = tool_name
        self.help_file_name = help_file_name
        self.spec = spec
        self.source_dir = source_dir
        self.toplevel: Optional[tk.Toplevel] = None
        self.worker_thread: Optional[threading.Thread] = None
        self.cancel_event = threading.Event()
        self.result_queue: queue.Queue = queue.Queue()
        self.running = False
        self._original_close = None

        # Resolve executable path
        self.exe_path = self._resolve_exe()

        # Add menu item
        self._add_menu_item()

        # Override close
        self._original_close = self.app.protocol('WM_DELETE_WINDOW')
        self.app.protocol('WM_DELETE_WINDOW', self._on_root_close)

    def _resolve_exe(self) -> str:
        """Resolve bundled executable path."""
        try:
            exe_name = BUNDLED_TOOLS[self.tool_name]
        except (KeyError, TypeError):
            raise ValueError('未対応の同梱ツールです。') from None
        if getattr(sys, 'frozen', False):
            base = sys._MEIPASS
        else:
            if self.source_dir:
                base = str(self.source_dir)
            else:
                base = os.path.dirname(os.path.abspath(__file__))

        exe_path = os.path.join(base, exe_name)
        return exe_path

    def _add_menu_item(self):
        """Add '詳細機能' menu item to existing root."""
        if not hasattr(self.app, 'menubar'):
            self.app.menubar = tk.Menu(self.app)
            self.app.config(menu=self.app.menubar)

        if not hasattr(self.app, 'advanced_menu'):
            self.app.advanced_menu = tk.Menu(self.app.menubar, tearoff=0)
            self.app.menubar.add_cascade(label="詳細機能", menu=self.app.advanced_menu)

        self.app.advanced_menu.add_command(
            label="開く",
            command=self.open_window
        )

    def open_window(self):
        """Open the advanced functions Toplevel window."""
        if self.toplevel and self.toplevel.winfo_exists():
            self.toplevel.lift()
            return

        self.toplevel = tk.Toplevel(self.app)
        self.toplevel.title(f"{self.tool_name} - 詳細機能")
        self.toplevel.geometry("1100x820")
        self.toplevel.minsize(900, 740)
        self._stdin_bytes = None
        for name in ("result_text", "result_frame", "save_btn", "_last_result"):
            if hasattr(self, name): delattr(self, name)

        # Build UI
        self._build_ui()
        self._clear_result()

        # Bind close
        self.toplevel.protocol('WM_DELETE_WINDOW', self._on_toplevel_close)

        # Poll queue
        self._poll_queue()

    def _build_ui(self):
        """Build the structured UI."""
        root = self.toplevel
        root.columnconfigure(0, weight=1)
        root.rowconfigure(0, weight=3)
        root.rowconfigure(1, weight=1)

        # Main frame
        main_frame = ttk.Frame(root, padding=5)
        main_frame.grid(row=0, column=0, sticky='nsew')
        main_frame.columnconfigure(0, weight=1)
        main_frame.rowconfigure(1, weight=1)

        # Top: Subcommand and presets
        top_frame = ttk.LabelFrame(main_frame, text="サブコマンドとプリセット", padding=5)
        top_frame.grid(row=0, column=0, sticky='ew', pady=(0, 5))
        top_frame.columnconfigure(1, weight=1)

        ttk.Label(top_frame, text="サブコマンド:").grid(row=0, column=0, sticky='w')
        self.subcommand_var = tk.StringVar()
        subcommands = self.spec.get('subcommands', [])
        self.subcommand_combo = ttk.Combobox(
            top_frame,
            textvariable=self.subcommand_var,
            values=[''] + subcommands,
            state='readonly'
        )
        self.subcommand_combo.grid(row=0, column=1, sticky='ew', padx=5)
        self.subcommand_combo.bind('<<ComboboxSelected>>', lambda event: self._update_preview())

        ttk.Label(top_frame, text="プリセット:").grid(row=1, column=0, sticky='w', pady=(5, 0))
        self.preset_var = tk.StringVar()
        presets = [ex['name'] for ex in self.spec.get('examples', [])]
        self.preset_combo = ttk.Combobox(
            top_frame,
            textvariable=self.preset_var,
            values=presets,
            state='readonly'
        )
        self.preset_combo.grid(row=1, column=1, sticky='ew', padx=5, pady=(5, 0))
        self.preset_combo.bind('<<ComboboxSelected>>', self._on_preset_select)

        # Middle: Options tree and argument tree
        mid_frame = ttk.Frame(main_frame)
        mid_frame.grid(row=1, column=0, sticky='nsew', pady=5)
        mid_frame.columnconfigure(0, weight=1)
        mid_frame.columnconfigure(1, weight=1)
        mid_frame.rowconfigure(0, weight=1)

        # Left: Option tree
        opt_frame = ttk.LabelFrame(mid_frame, text="オプション", padding=5)
        opt_frame.grid(row=0, column=0, sticky='nsew', padx=(0, 5))
        opt_frame.columnconfigure(0, weight=0)
        opt_frame.columnconfigure(1, weight=1)
        opt_frame.rowconfigure(1, weight=1)

        ttk.Label(opt_frame, text="フィルター:").grid(row=0, column=0, sticky='w')
        self.filter_var = tk.StringVar()
        self.filter_entry = ttk.Entry(opt_frame, textvariable=self.filter_var)
        self.filter_entry.grid(row=0, column=1, sticky='ew', padx=5)
        self.filter_entry.bind('<KeyRelease>', self._filter_options)

        self.option_tree = ttk.Treeview(opt_frame, columns=('flag', 'desc'), show='headings', height=6)
        self.option_tree.heading('flag', text='フラグ')
        self.option_tree.heading('desc', text='説明')
        self.option_tree.column('flag', width=150)
        self.option_tree.column('desc', width=250)
        self.option_tree.grid(row=1, column=0, columnspan=2, sticky='nsew', pady=(5, 0))
        option_scroll = ttk.Scrollbar(opt_frame, orient='vertical', command=self.option_tree.yview)
        option_scroll.grid(row=1, column=2, sticky='ns')
        self.option_tree.configure(yscrollcommand=option_scroll.set)

        # Populate option tree
        self._populate_option_tree()

        # Option value entry and append button
        opt_btn_frame = ttk.Frame(opt_frame)
        opt_btn_frame.grid(row=2, column=0, columnspan=2, sticky='ew', pady=(5, 0))
        opt_btn_frame.columnconfigure(1, weight=1)
        ttk.Label(opt_btn_frame, text='値（必要な場合）:').grid(row=0, column=0, padx=(0, 5))

        self.option_value_var = tk.StringVar()
        self.option_value_entry = ttk.Entry(opt_btn_frame, textvariable=self.option_value_var)
        self.option_value_entry.grid(row=0, column=1, sticky='ew', padx=(0, 5))

        ttk.Button(opt_btn_frame, text="追加", command=self._append_option).grid(row=0, column=2)

        # Right: Argument tree
        arg_frame = ttk.LabelFrame(mid_frame, text="引数", padding=5)
        arg_frame.grid(row=0, column=1, sticky='nsew', padx=(5, 0))
        arg_frame.columnconfigure(0, weight=1)
        arg_frame.rowconfigure(1, weight=1)

        self.arg_tree = ttk.Treeview(arg_frame, columns=('token',), show='headings', height=6)
        self.arg_tree.heading('token', text='引数（1項目につき1個）')
        self.arg_tree.column('token', width=300)
        self.arg_tree.grid(row=1, column=0, sticky='nsew', pady=(5, 0))

        # Argument buttons
        arg_btn_frame = ttk.Frame(arg_frame)
        arg_btn_frame.grid(row=2, column=0, sticky='ew', pady=(5, 0))

        ttk.Button(arg_btn_frame, text="追加", command=self._add_arg_token).grid(row=0, column=0, padx=2)
        ttk.Button(arg_btn_frame, text="削除", command=self._remove_arg_token).grid(row=0, column=1, padx=2)
        ttk.Button(arg_btn_frame, text="上へ", command=self._move_arg_up).grid(row=0, column=2, padx=2)
        ttk.Button(arg_btn_frame, text="下へ", command=self._move_arg_down).grid(row=0, column=3, padx=2)

        # Additional positional token entry
        pos_frame = ttk.Frame(arg_frame)
        pos_frame.grid(row=3, column=0, sticky='ew', pady=(5, 0))
        pos_frame.columnconfigure(0, weight=1)

        self.pos_token_var = tk.StringVar()
        self.pos_token_entry = ttk.Entry(pos_frame, textvariable=self.pos_token_var)
        self.pos_token_entry.grid(row=0, column=0, sticky='ew', padx=(0, 5))
        ttk.Button(pos_frame, text="追加", command=self._add_pos_token).grid(row=0, column=1)

        # File/directory picker
        ttk.Button(arg_frame, text="ファイル選択", command=self._pick_file).grid(row=4, column=0, sticky='w', pady=(5, 0))

        # Bottom: Stdin, cwd, preview, run
        bottom_frame = ttk.LabelFrame(main_frame, text="実行設定", padding=5)
        bottom_frame.grid(row=2, column=0, sticky='ew', pady=(5, 0))
        bottom_frame.columnconfigure(0, weight=1)

        # Stdin
        ttk.Label(bottom_frame, text="標準入力 (UTF-8):").grid(row=0, column=0, sticky='w')
        self.stdin_text = tk.Text(bottom_frame, height=3, wrap='word')
        self.stdin_text.grid(row=1, column=0, sticky='ew', pady=(2, 5))
        input_buttons = ttk.Frame(bottom_frame)
        input_buttons.grid(row=0, column=0, sticky='e')
        ttk.Button(input_buttons, text='標準入力をファイルから読込', command=self._load_stdin).pack(side='left')
        ttk.Button(input_buttons, text='入力をクリア', command=self._clear_stdin).pack(side='left', padx=4)

        # Working directory
        cwd_frame = ttk.Frame(bottom_frame)
        cwd_frame.grid(row=2, column=0, sticky='ew', pady=(0, 5))
        cwd_frame.columnconfigure(1, weight=1)

        ttk.Label(cwd_frame, text="作業フォルダー:").grid(row=0, column=0, sticky='w')
        self.cwd_var = tk.StringVar()
        default_cwd = r'C:\Users\Public\Documents'
        if not os.path.isdir(default_cwd):
            default_cwd = os.getcwd()
        self.cwd_var.set(default_cwd)
        self.cwd_entry = ttk.Entry(cwd_frame, textvariable=self.cwd_var)
        self.cwd_entry.grid(row=0, column=1, sticky='ew', padx=5)
        ttk.Button(cwd_frame, text="参照", command=self._browse_cwd).grid(row=0, column=2)

        # Command preview
        ttk.Label(bottom_frame, text="コマンドプレビュー:").grid(row=3, column=0, sticky='w')
        self.preview_text = tk.Text(bottom_frame, height=2, wrap='word', state='disabled')
        self.preview_text.grid(row=4, column=0, sticky='ew', pady=(2, 5))

        # Run button
        self.run_btn = ttk.Button(bottom_frame, text="実行", command=self._run)
        self.run_btn.grid(row=5, column=0, sticky='w', pady=(5, 0))

        # Help button
        ttk.Button(bottom_frame, text="ヘルプ表示", command=self._show_help).grid(row=5, column=0, sticky='e', pady=(5, 0), padx=(5, 0))

        # Update preview
        ttk.Button(bottom_frame, text='停止', command=self.cancel_event.set).grid(row=5, column=0, padx=70, sticky='w')
        ttk.Button(arg_frame, text='フォルダー選択', command=self._pick_directory).grid(row=4, column=0, sticky='e')
        self._update_preview()

    def _populate_option_tree(self):
        """Populate option tree from spec."""
        self.option_tree.delete(*self.option_tree.get_children())
        for opt in self.spec.get('options', []):
            self.option_tree.insert('', 'end', values=(opt.get('flag', ''), opt.get('description', '')))

    def _filter_options(self, event=None):
        """Filter options based on filter text."""
        filter_text = self.filter_var.get().lower()
        self.option_tree.delete(*self.option_tree.get_children())
        for opt in self.spec.get('options', []):
            flag = opt.get('flag', '').lower()
            desc = opt.get('description', '').lower()
            if filter_text in flag or filter_text in desc:
                self.option_tree.insert('', 'end', values=(opt.get('flag', ''), opt.get('description', '')))

    def _append_option(self):
        """Append selected option to argument tree."""
        selection = self.option_tree.selection()
        if not selection:
            return

        item = self.option_tree.item(selection[0])
        flag = item['values'][0]
        if any(o['flag'] == flag and o.get('blocked') for o in self.spec['options']):
            messagebox.showinfo('詳細機能', 'この機能は制限対象です。同梱ヘルプと機能差分表を参照してください。', parent=self.toplevel)
            return
        value = self.option_value_var.get()

        if value:
            self._add_to_arg_tree(flag)
            self._add_to_arg_tree(value)
        else:
            self._add_to_arg_tree(flag)

        self.option_value_var.set('')
        self._update_preview()

    def _add_to_arg_tree(self, token: str):
        """Add token to argument tree."""
        self.arg_tree.insert('', 'end', values=(token,))

    def _add_arg_token(self):
        """Add token from pos_token_entry."""
        token = self.pos_token_var.get().strip()
        if token:
            self._add_to_arg_tree(token)
            self.pos_token_var.set('')
            self._update_preview()

    def _add_pos_token(self):
        """Add positional token."""
        self._add_arg_token()

    def _remove_arg_token(self):
        """Remove selected argument token."""
        selection = self.arg_tree.selection()
        if selection:
            self.arg_tree.delete(selection)
            self._update_preview()

    def _move_arg_up(self):
        """Move selected argument up."""
        selection = self.arg_tree.selection()
        if not selection:
            return
        item = selection[0]
        children = self.arg_tree.get_children()
        idx = children.index(item)
        if idx > 0:
            self.arg_tree.move(item, '', idx - 1)

    def _move_arg_down(self):
        """Move selected argument down."""
        selection = self.arg_tree.selection()
        if not selection:
            return
        item = selection[0]
        children = self.arg_tree.get_children()
        idx = children.index(item)
        if idx < len(children) - 1:
            self.arg_tree.move(item, '', idx + 1)

    def _pick_file(self):
        """Pick file or directory."""
        path = filedialog.askopenfilename(parent=self.toplevel)
        if path:
            self._add_to_arg_tree(path)
            self._update_preview()

    def _browse_cwd(self):
        """Browse for working directory."""
        path = filedialog.askdirectory()
        if path:
            self.cwd_var.set(path)

    def _on_preset_select(self, event=None):
        """Load preset arguments."""
        preset_name = self.preset_var.get()
        for ex in self.spec.get('examples', []):
            if ex['name'] == preset_name:
                # Clear current args
                self.arg_tree.delete(*self.arg_tree.get_children())
                args = list(ex.get('args', []))
                self.subcommand_var.set(args.pop(0) if args and args[0] in self.spec.get('subcommands', []) else '')
                for arg in args:
                    self._add_to_arg_tree(arg)
                # Set stdin if provided
                stdin = ex.get('stdin', '')
                self._clear_stdin()
                if stdin:
                    self.stdin_text.insert('1.0', stdin)
                self._update_preview()
                break

    def _update_preview(self):
        """Update command preview."""
        args = []
        for item in self.arg_tree.get_children():
            values = self.arg_tree.item(item, 'values')
            if values:
                args.append(values[0])

        # Add subcommand if selected
        subcmd = self.subcommand_var.get()
        if subcmd:
            args = [subcmd] + args

        try:
            cmd = build_command(
                self.exe_path,
                args,
                mandatory_args=tuple(self.spec.get('mandatory_args', [])),
                blocked_flags=tuple(self.spec.get('blocked_flags', []))
            )
            preview = subprocess.list2cmdline(self._preview_tokens(cmd))
        except Exception as e:
            preview = f"エラー: {e}"

        self.preview_text.config(state='normal')
        self.preview_text.delete('1.0', 'end')
        self.preview_text.insert('1.0', preview)
        self.preview_text.config(state='disabled')

    def _show_help(self):
        """Show full help in separate window."""
        help_win = tk.Toplevel(self.toplevel)
        help_win.title(f"{self.tool_name} - ヘルプ")
        help_win.geometry("600x400")

        text = tk.Text(help_win, wrap='word')
        text.pack(fill='both', expand=True, padx=5, pady=5)

        # Load help file
        try:
            help_path = resource_path(self.help_file_name, self.source_dir)
            with open(help_path, 'r', encoding='utf-8', errors='replace') as f:
                help_text = f.read()
            text.insert('1.0', _strip_ansi(help_text))
        except Exception as e:
            text.insert('1.0', f"ヘルプを読み込めませんでした: {e}")

        text.config(state='disabled')

    def _run(self):
        """Run the command."""
        if self.running:
            return

        # Snapshot UI state
        args = []
        for item in self.arg_tree.get_children():
            values = self.arg_tree.item(item, 'values')
            if values:
                args.append(values[0])

        subcmd = self.subcommand_var.get()
        if subcmd:
            args = [subcmd] + args

        stdin_data = self._stdin_bytes if self._stdin_bytes is not None else self.stdin_text.get('1.0', 'end-1c').encode('utf-8')
        cwd = self.cwd_var.get()

        # Clear previous result
        self._clear_result()

        self.running = True
        self.run_btn.config(state='disabled')
        self.cancel_event.clear()

        self.worker_thread = threading.Thread(
            target=self._worker,
            args=(args, stdin_data, cwd),
            daemon=True
        )
        self.worker_thread.start()

    def _worker(self, args: List[str], stdin_data: bytes, cwd: str):
        """Worker thread for execution."""
        try:
            result = execute(
                exe=self.exe_path,
                args=args,
                stdin_data=stdin_data,
                cwd=cwd,
                cancel_event=self.cancel_event,
                timeout=300,
                max_output=16 * 1024 * 1024,
                mandatory_args=tuple(self.spec.get('mandatory_args', [])),
                blocked_flags=tuple(self.spec.get('blocked_flags', []))
            )
            self.result_queue.put(('result', result))
        except Exception as e:
            self.result_queue.put(('error', str(e)))
        finally:
            self.result_queue.put(('done', None))

    def _poll_queue(self):
        """Poll result queue on UI thread."""
        try:
            while True:
                msg_type, data = self.result_queue.get_nowait()
                if msg_type == 'result':
                    self._show_result(data)
                elif msg_type == 'error':
                    self._show_error(data)
                elif msg_type == 'done':
                    self.running = False
                    self.run_btn.config(state='normal')
        except queue.Empty:
            pass

        if self.toplevel and self.toplevel.winfo_exists():
            self.toplevel.after(100, self._poll_queue)

    def _clear_result(self):
        """Clear previous result display."""
        # Add result display area if not exists
        if not hasattr(self, 'result_text'):
            self.result_frame = ttk.LabelFrame(self.toplevel, text="結果", padding=5)
            self.result_frame.grid(row=1, column=0, sticky='nsew', padx=5, pady=5)
            self.result_frame.rowconfigure(0, weight=1)
            self.result_frame.columnconfigure(0, weight=1)
            self.result_text = tk.Text(self.result_frame, height=6, wrap='word')
            self.result_text.grid(row=0, column=0, sticky='nsew')

        self._last_result = None
        if hasattr(self, 'save_btn'): self.save_btn.config(state='disabled')
        self.result_text.delete('1.0', 'end')

    def _show_result(self, result: Dict[str, Any]):
        """Display execution result."""
        self._clear_result()

        stdout = result['stdout'][:512*1024].decode('utf-8', errors='replace')
        stderr = result['stderr'][:512*1024].decode('utf-8', errors='replace')
        returncode = result['returncode']

        text = f"終了コード: {returncode}（0以外の意味は元ツールのヘルプを確認してください）\n\n"
        if max(len(result['stdout']),len(result['stderr'])) > 512*1024:
            text += '表示は各先頭512 KiBまでです。保存時は標準出力全体を保持します。\n'
        text += f"=== 標準出力 ===\n{_strip_ansi(stdout)}\n\n"
        text += f"=== 標準エラー ===\n{_strip_ansi(stderr)}\n"

        self.result_text.insert('1.0', text)

        # Add save button
        if not hasattr(self, 'save_btn'):
            self.save_btn = ttk.Button(self.result_frame, text="標準出力を保存（元のバイト列）", command=self._save_output)
            self.save_btn.grid(row=1, column=0, sticky='w', pady=(5, 0))

        self._last_result = result
        self.save_btn.config(state='normal')

    def _show_error(self, error: str):
        """Display error message."""
        self._clear_result()
        self.result_text.insert('1.0', f"エラー: {error}")

    def _save_output(self):
        """Save binary output."""
        if self.running or not getattr(self, '_last_result', None):
            return

        path = filedialog.asksaveasfilename(
            defaultextension='.txt',
            filetypes=[("テキスト", "*.txt"), ("バイナリ", "*.bin"), ("すべてのファイル", "*.*")]
        )
        if not path:
            return

        # Check if file exists
        if os.path.exists(path):
            if not messagebox.askyesno("確認", "ファイルを上書きしますか？"):
                return

        try:
            with open(path, 'wb') as f:
                f.write(self._last_result['stdout'])
            messagebox.showinfo("保存", "保存しました")
        except Exception as e:
            messagebox.showerror("エラー", f"保存に失敗しました: {e}")

    def _pick_directory(self):
        path = filedialog.askdirectory(parent=self.toplevel)
        if path:
            self._add_to_arg_tree(path)
            self._update_preview()

    def _clear_stdin(self):
        self._stdin_bytes = None
        self.stdin_text.config(state='normal')
        self.stdin_text.delete('1.0', 'end')

    def _load_stdin(self):
        path = filedialog.askopenfilename(parent=self.toplevel)
        if not path: return
        try:
            with open(path, 'rb') as handle:
                data = handle.read(2*1024*1024+1)
            if len(data)>2*1024*1024: raise ValueError('標準入力ファイルは2 MiBまでです。')
        except (OSError, ValueError):
            self._show_error('標準入力ファイルを読み込めません。2 MiBまでの読み取り可能なファイルを指定してください。')
            return
        self._stdin_bytes = data
        self.stdin_text.config(state='normal')
        self.stdin_text.delete('1.0','end')
        self.stdin_text.insert('1.0', f'ファイル: {Path(path).name}（{len(data):,}バイト）\n実行時はファイルの元のバイト列を使います。')
        self.stdin_text.config(state='disabled')

    def _preview_tokens(self, command):
        tokens = [Path(command[0]).name]
        hide_next = False
        sensitive = set(self.spec.get('sensitive_flags', []))
        for token in command[1:]:
            if hide_next:
                tokens.append('***'); hide_next = False; continue
            flag = token.split('=', 1)[0]
            if flag in sensitive:
                tokens.append(flag + '=***' if '=' in token else flag)
                hide_next = '=' not in token
            elif token.lower().startswith(('authorization:', 'cookie:', 'proxy-authorization:')):
                tokens.append(token.split(':',1)[0]+':***')
            else:
                tokens.append(token)
        return tokens

    def _on_toplevel_close(self):
        self.cancel_event.set()
        if self.worker_thread and self.worker_thread.is_alive():
            self.app.after(50, self._on_toplevel_close)
            return
        self.running = False
        self._stdin_bytes = None
        if self.toplevel:
            self.toplevel.destroy()
            self.toplevel = None
        while not self.result_queue.empty(): self.result_queue.get_nowait()

    def _on_root_close(self):
        self.cancel_event.set()
        if self.worker_thread and self.worker_thread.is_alive():
            self.app.after(50, self._on_root_close)
            return
        if self._original_close:
            self.app.tk.call(self._original_close)
        else:
            self.app.destroy()


def attach(app, source_dir=None):
    with open(resource_path('advanced-spec.json', source_dir), encoding='utf-8') as handle:
        spec=json.load(handle)
    return AdvancedController(app, spec['tool'], 'upstream-help.txt', spec, source_dir)
