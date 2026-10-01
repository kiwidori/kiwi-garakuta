import sys,json
from pathlib import Path
from tkinter import ttk,filedialog,messagebox
import tkinter as tk
sys.path.insert(0,str(Path(__file__).resolve().parent.parent/'common'))
from workbench import App
import runtime
from ansi_renderer import render_ansi

class BytesApp(App):
    def __init__(self,profile,source_dir):
        self._rendered=None
        super().__init__(profile,source_dir)

    def _build_ui(self):
        super()._build_ui()
        self.tabs.pack_configure(expand=False)
        for name in self.tabs.tabs():
            for child in self.tabs.nametowidget(name).winfo_children():
                if isinstance(child,tk.Canvas):child.configure(height=150)
        for row in self.path_list.master.winfo_children():
            for button in row.winfo_children():
                if isinstance(button,ttk.Button) and button.cget('text')=='フォルダーを追加':button.destroy()
        self.path_list.master.configure(text='対象ファイル（1つ選択）')
        self.in_text.master.configure(text='入力データ（ファイル操作では空、16進数は00 7f ffの形式）')
        self.out_text.configure(font=('Consolas',11),background='#111827',foreground='#f8fafc',wrap='none')
        ttk.Button(self.run_btn.master,text='デモ',command=self._demo).pack(side='left')
        ttk.Button(self.run_btn.master,text='プレーン保存',command=self._save_plain).pack(side='left')

    def _demo(self):
        if self.worker and self.worker.is_alive():return
        self._clear_paths()
        self.mode_var.set('16進数入力を表示')
        self.in_text.delete('1.0','end')
        self.in_text.insert('1.0','4b 69 77 69 20 48 65 78 79 6c 0a 00 7f 80 fe ff')
        for field in self.profile['fields']:self.values[field['flag']].set(field.get('default',False if field['type']=='bool' else ''))

    def _poll_queue(self):
        super()._poll_queue()
        result=self.last_result
        if result is not None and result is not self._rendered and 'stdout' in result:
            self._rendered=result
            text=result['stdout'].decode('utf8','replace')
            if result.get('stderr'):text+='\n'+runtime._strip_ansi(result['stderr'].decode('utf8','replace'))
            render_ansi(self.out_text,text)

    def _save_plain(self):
        if not self.last_result or 'stdout' not in self.last_result:return
        name=filedialog.asksaveasfilename(defaultextension='.txt')
        if not name:return
        if Path(name).exists() and not messagebox.askyesno('確認','ファイルが存在します。上書きしますか？'):return
        try:Path(name).write_bytes(runtime._strip_ansi(self.last_result['stdout'].decode('utf8','replace')).encode('utf8'))
        except OSError as error:messagebox.showerror('保存エラー',str(error))

    def _worker(self, args, stdin_data, mode_def):
        try:
            flags = args[:args.index('--')] if '--' in args else args
            is_info = any(a in ('--version', '--help', '--print-color-table') or a.startswith('--completion') for a in flags)
            if not is_info and mode_def.get('files'):
                idx = args.index('--')
                if len(args[idx + 1:]) != 1 or not Path(args[idx + 1]).is_file():
                    raise ValueError('ファイルが1つ必要です。')
                stdin_data = None
            elif not is_info and mode_def.get('hex_input'):
                text = stdin_data.decode('utf8')
                data = bytes.fromhex(text)
                if len(data) > 2 * 1024 * 1024:
                    raise ValueError('解析後のサイズが大きすぎます。')
                stdin_data = data
            elif is_info:
                    stdin_data = b''
            result = runtime.execute(self.exe_path, args, stdin_data=stdin_data, cancel_event=self.cancel_event)
            flags_before_dd = args[:args.index('--')] if '--' in args else args
            result['extension'] = '.h' if '--include' in flags_before_dd else '.txt'
            rc = result['returncode']
            self.q.put(('done', rc, result['stdout'], result['stderr'], rc == 0, result))
        except Exception as error:
            self.q.put(('error', str(error)))

if __name__=='__main__':
    source=Path(__file__).resolve().parent
    profile=json.loads(Path(runtime.resource_path('profile.json',source)).read_text(encoding='utf8'))
    BytesApp(profile,source).root.mainloop()
