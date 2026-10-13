import sys,json,threading,io,zipfile,tempfile,time,os
from pathlib import Path
import tkinter as tk
from tkinter import ttk,filedialog,messagebox
sys.path.insert(0,str(Path(__file__).resolve().parent.parent/'common'))
from workbench import App,MAX_IN
import runtime

def build_sd_args(values, preview=False):
    if any('\x00' in str(values.get(k, '')) for k in ('find', 'replace')):
        raise ValueError('検索と置換にNULは使えません。')
    try:
        limit = int(str(values.get('--max-replacements', '0')))
        if not 0 <= limit <= 2147483647: raise ValueError
    except (ValueError, TypeError):
        raise ValueError('置換回数は0から2147483647の整数で指定してください。')
    values = dict(values)
    values['--max-replacements'] = str(limit)
    if (values.get('flag-c') and values.get('flag-i')) or (values.get('flag-e') and values.get('flag-m')):
        raise ValueError('c/iとe/mは同時に指定できません。')
    flags = []
    if values.get("--fixed-strings"): flags.append("-F")
    mr = str(values.get("--max-replacements", "0"))
    if mr != "0": flags.extend(["-n", mr])
    if values.get("--across"): flags.append("--across")
    fstr = ""
    for k in ["c","e","i","m","s","w"]:
        if values.get(f"flag-{k}"): fstr += k
    if fstr: flags.extend(["-f", fstr])
    if preview: flags.append("--preview")
    find = values.get("find", "")
    repl = values.get("replace", "")
    return flags + ["--", find, repl]

def process(exe, args, stdin_data, paths, cancel_event):
    deadline = time.monotonic() + 300
    if cancel_event and cancel_event.is_set():
        raise InterruptedError('処理を停止しました。')
    if not paths:
        result = runtime.execute(exe, args, stdin_data=stdin_data, cancel_event=cancel_event)
        result['extension'] = '.txt'
        return result
    if len(paths) > 2000:
        raise ValueError('ファイルは2000件までです。')
    inputs = []
    seen = set()
    total_in = 0
    for value in paths:
        if cancel_event and cancel_event.is_set():
            raise InterruptedError('処理を停止しました。')
        if time.monotonic() >= deadline:
            raise TimeoutError('時間制限に達しました。')
        path = Path(value).absolute()
        if not path.is_file() or any(p.is_symlink() or p.is_junction() for p in (path, *path.parents)):
            raise ValueError('通常のファイルだけを指定してください。リンクは扱えません。')
        key = str(path.resolve()).casefold()
        if key in seen:
            raise ValueError('同じファイルが重複しています。')
        seen.add(key)
        with path.open('rb') as handle:
            data = handle.read(2 * 1024 * 1024 + 1)
        if len(data) > 2 * 1024 * 1024:
            raise ValueError('各ファイルは2 MiBまでです。')
        try:
            data.decode('utf8')
        except UnicodeDecodeError as error:
            raise ValueError('ファイルはUTF-8で指定してください。') from error
        total_in += len(data)
        if total_in > 64 * 1024 * 1024:
            raise ValueError('入力合計は64 MiBまでです。')
        inputs.append((path.name, data))
    preview = '--preview' in args[:args.index('--')] if '--' in args else False
    outputs = []
    errors = bytearray()
    total_out = 0
    for index, (name, data) in enumerate(inputs, 1):
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError('時間制限に達しました。')
        result = runtime.execute(exe, args, stdin_data=data, cancel_event=cancel_event, timeout=remaining)
        if result['returncode'] != 0:
            result['extension'] = '.txt'
            return result
        errors.extend(result['stderr'])
        if len(errors) > 16 * 1024 * 1024:
            raise ValueError('エラー出力の上限を超えました。')
        output = result['stdout']
        total_out += len(output)
        if total_out > 64 * 1024 * 1024:
            raise ValueError('出力合計は64 MiBまでです。')
        outputs.append((f'{index:04d}_{name}', output))
    if cancel_event and cancel_event.is_set():
        raise InterruptedError('処理を停止しました。')
    if preview:
        data = b''.join(('----- ' + name + ' -----\n').encode('utf8') + value + b'\n' for name, value in outputs)
        if len(data) > 16 * 1024 * 1024:
            raise ValueError('プレビューは16 MiBまでです。')
        return dict(stdout=data, stderr=bytes(errors), returncode=0, extension='.txt')
    if len(outputs) == 1:
        return dict(stdout=outputs[0][1], stderr=bytes(errors), returncode=0, extension='.txt')
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, 'w', zipfile.ZIP_DEFLATED) as archive:
        for name, data in outputs:
            if cancel_event and cancel_event.is_set():
                raise InterruptedError('処理を停止しました。')
            if time.monotonic() >= deadline:
                raise TimeoutError('時間制限に達しました。')
            archive.writestr(name, data)
            if stream.tell() > 16 * 1024 * 1024:
                raise ValueError('保存ZIPは16 MiBまでです。')
    data = stream.getvalue()
    if len(data) > 16 * 1024 * 1024:
        raise ValueError('保存ZIPは16 MiBまでです。')
    return dict(stdout=data, stderr=bytes(errors), returncode=0, extension='.zip', display=f'{len(outputs)}ファイルを置換しました。結果は番号付きZIPとして保存できます。\n' + '\n'.join(name for name, _ in outputs))


class ReplaceApp(App):
    def _build_ui(self):
        super()._build_ui()
        self.tabs.pack_configure(expand=False)
        for name in self.tabs.tabs():
            frame = self.tabs.nametowidget(name)
            canvas = next((c for c in frame.winfo_children() if isinstance(c, tk.Canvas)), None)
            if canvas:
                canvas.configure(height=180)
        btns = self.path_list.master
        for w in [child for row in btns.winfo_children() for child in row.winfo_children()]:
            if isinstance(w, ttk.Button) and w.cget('text') == 'フォルダーを追加':
                w.destroy()
        in_frame = self.in_text.master
        in_frame.configure(text='テキスト入力（ファイル操作では空にする）')
        ttk.Button(self.run_btn.master, text='デモ', command=self._demo).pack(side='left')

    def _demo(self):
        if self.worker and self.worker.is_alive():
            return
        self.mode_var.set(self.profile['modes'][0]['label'])
        self._clear_paths()
        self.in_text.delete('1.0', 'end')
        self.in_text.insert('1.0', 'cat cat\n猫 cat\n')
        for f in self.profile.get('fields', []):
            flag = f['flag']
            if f['type'] == 'bool':
                self.values[flag].set(bool(f.get('default', False)))
            else:
                default = f.get('default', '')
                if flag == 'find':
                    default = 'cat'
                elif flag == 'replace':
                    default = 'dog'
                elif flag == '--max-replacements':
                    default = '0'
                self.values[flag].set(str(default))

    def run(self):
        if self.worker and self.worker.is_alive():
            return
        mode = self.mode_var.get()
        m = next((x for x in self.profile['modes'] if x['label'] == mode), None)
        if not m:
            return
        if mode in ('ヘルプ', 'バージョン'):
            args = ['--help' if mode == 'ヘルプ' else '--version']
            stdin_data = b''
            paths = []
        else:
            text_str = self.in_text.get('1.0', 'end-1c')
            if m.get('stdin') and self.paths:
                messagebox.showerror('入力', 'テキスト操作ではファイル一覧をクリアしてください。')
                return
            if m.get('files') and text_str:
                messagebox.showerror('入力', 'ファイル操作ではテキスト入力を空にしてください。')
                return
            has_paths = len(self.paths) > 0
            use_stdin = False
            stdin_data = b''
            if m.get('stdin'):
                if not has_paths:
                    stdin_data = text_str.encode('utf-8')
                    use_stdin = True
            elif m.get('files'):
                if not has_paths:
                    messagebox.showerror('入力', '対象ファイルが指定されていません。')
                    return
            if use_stdin and len(stdin_data) > MAX_IN:
                messagebox.showerror('入力', '入力サイズが2MiBを超えています。')
                return
            paths = []
            for p in self.paths:
                ap = os.path.abspath(p)
                if '\x00' in ap or not os.path.exists(ap):
                    messagebox.showerror('入力', '無効なパスです。')
                    return
                paths.append(ap)
        values = {k: v.get() for k, v in self.values.items()}
        try:
            if mode not in ('ヘルプ', 'バージョン'):
                args = build_sd_args(values, preview=('プレビュー' in mode))
            else:
                args = ['--help' if mode == 'ヘルプ' else '--version']
        except (ValueError, UnicodeEncodeError) as e:
            messagebox.showerror('入力エラー', str(e))
            return
        self.cancel_event.clear()
        self.last_result = None
        self.run_btn.config(state='disabled')
        self.stop_btn.config(state='normal')
        self.status_var.set('実行中...')
        self.out_text.config(state='normal')
        self.out_text.delete('1.0', 'end')
        self.out_text.config(state='disabled')
        self.worker = threading.Thread(target=self._replace_worker, args=(args, stdin_data, paths), daemon=True)
        self.worker.start()

    def _replace_worker(self, args, stdin_data, paths):
        try:
            result = process(self.exe_path, args, stdin_data, paths, self.cancel_event)
            rc, out, err = result['returncode'], result['stdout'], result['stderr']
            self.q.put(('done', rc, out, err, rc == 0, result))
        except Exception as e:
            self.q.put(('error', str(e)))

if __name__=='__main__':
    source=Path(__file__).resolve().parent
    profile=json.loads(Path(runtime.resource_path('profile.json',source)).read_text(encoding='utf8'))
    ReplaceApp(profile,source).root.mainloop()
