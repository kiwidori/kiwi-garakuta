import sys, json, re, os, threading, queue, tkinter as tk
from tkinter import ttk, filedialog, messagebox
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'common'))
import workbench
from workbench import App
import runtime
SGR_RE = re.compile('\\x1b\\[([0-9;]*)m')
MAX_RENDER = 128 * 1024

def render_ansi(widget, text):
    if not isinstance(text, str):
        return
    raw_bytes = text.encode('utf-8', 'replace')
    truncated = len(raw_bytes) > MAX_RENDER
    if truncated:
        text = raw_bytes[:MAX_RENDER].decode('utf-8', 'ignore') + '\n... (表示省略)'
    for tag in widget.tag_names():
        if tag.startswith('glow_'):
            try:
                widget.tag_delete(tag)
            except Exception:
                pass
    base_fg = str(widget.cget('foreground')) or '#000000'
    base_bg = str(widget.cget('background')) or '#ffffff'
    palette16 = ['#000000', '#800000', '#008000', '#808000', '#000080', '#800080', '#008080', '#c0c0c0', '#808080', '#ff0000', '#00ff00', '#ffff00', '#0000ff', '#ff00ff', '#00ffff', '#ffffff']

    def _color_256(n):
        n = max(0, min(255, int(n)))
        if n < 16:
            return palette16[n]
        if n < 232:
            levels = [0, 95, 135, 175, 215, 255]
            idx = n - 16
            r = levels[idx // 36 % 6]
            g = levels[idx % 36 // 6 % 6]
            b = levels[idx % 6]
            return f'#{r:02x}{g:02x}{b:02x}'
        v = max(0, min(255, 8 + (n - 232) * 10))
        return f'#{v:02x}{v:02x}{v:02x}'

    def _rgb_hex(r, g, b):
        r = max(0, min(255, int(r)))
        g = max(0, min(255, int(g)))
        b = max(0, min(255, int(b)))
        return f'#{r:02x}{g:02x}{b:02x}'

    def _font_tuple(attrs):
        style = 'normal'
        if attrs['bold'] and attrs['italic']:
            style = 'bold italic'
        elif attrs['bold']:
            style = 'bold'
        elif attrs['italic']:
            style = 'italic'
        return ('Consolas', 11, style)

    def _make_tag(attrs):
        key = (attrs['bold'], attrs['italic'], attrs['underline'], attrs['strike'], attrs['fg'], attrs['bg'])
        if key in tag_cache:
            return tag_cache[key]
        if len(tag_cache) >= 255:
            return 'glow_base'
        name = f'glow_{len(tag_cache)}'
        opts = {'font': _font_tuple(attrs), 'foreground': attrs['fg'] or base_fg, 'background': attrs['bg'] or base_bg}
        if attrs['underline']:
            opts['underline'] = True
        opts['overstrike'] = attrs['strike']
        widget.tag_configure(name, **opts)
        tag_cache[key] = name
        return name

    def _apply_sgr(params):
        nonlocal attrs
        i = 0
        while i < len(params):
            p = params[i] if params[i] != '' else '0'
            try:
                v = int(p)
            except ValueError:
                i += 1
                continue
            if v == 0:
                attrs = {'bold': False, 'italic': False, 'underline': False, 'strike': False, 'fg': None, 'bg': None}
            elif v == 1:
                attrs['bold'] = True
            elif v in (2, 22):
                attrs['bold'] = False
            elif v == 3:
                attrs['italic'] = True
            elif v == 23:
                attrs['italic'] = False
            elif v == 4:
                attrs['underline'] = True
            elif v == 24:
                attrs['underline'] = False
            elif v == 9:
                attrs['strike'] = True
            elif v == 29:
                attrs['strike'] = False
            elif 30 <= v <= 37:
                attrs['fg'] = palette16[v - 30]
            elif 90 <= v <= 97:
                attrs['fg'] = palette16[v - 90 + 8]
            elif v == 39:
                attrs['fg'] = None
            elif 40 <= v <= 47:
                attrs['bg'] = palette16[v - 40]
            elif 100 <= v <= 107:
                attrs['bg'] = palette16[v - 100 + 8]
            elif v == 49:
                attrs['bg'] = None
            elif v in (38, 48):
                target = 'fg' if v == 38 else 'bg'
                if i + 2 < len(params) and params[i + 1] == '5':
                    try:
                        n = int(params[i + 2])
                        attrs[target] = _color_256(n)
                        i += 2
                    except ValueError:
                        pass
                elif i + 4 < len(params) and params[i + 1] == '2':
                    try:
                        r, g, b = (int(params[i + 2]), int(params[i + 3]), int(params[i + 4]))
                        attrs[target] = _rgb_hex(r, g, b)
                        i += 4
                    except ValueError:
                        pass
            i += 1
    text = runtime.OSC_RE.sub('', text)
    sgr_re = re.compile('\\x1b\\[([0-9;]*)m')
    attrs = {'bold': False, 'italic': False, 'underline': False, 'strike': False, 'fg': None, 'bg': None}
    tag_cache = {}
    widget.tag_configure('glow_base', font=('Consolas', 11), foreground=base_fg, background=base_bg)
    try:
        widget.config(state='normal')
        widget.delete('1.0', 'end')
        pos = 0
        for m in sgr_re.finditer(text):
            if m.start() > pos:
                span = runtime._strip_ansi(text[pos:m.start()])
                tag_name = _make_tag(attrs)
                widget.insert('end', span, (tag_name,))
            _apply_sgr(m.group(1).split(';'))
            pos = m.end()
        if pos < len(text):
            span = runtime._strip_ansi(text[pos:])
            tag_name = _make_tag(attrs)
            widget.insert('end', span, (tag_name,))
    finally:
        widget.config(state='disabled')

class MarkdownApp(App):

    def _load_demo(self):
        self.mode_var.set('貼り付けたMarkdownを表示')
        self.paths=[]
        self.path_list.delete(0,'end')
        demo = '# きういMarkdown\n\n**太字**と*斜体*\n\n|項目|値|\n|---|---|\n|例|42|\n\n```python\nprint("hello")\n```'
        self.in_text.delete('1.0', 'end')
        self.in_text.insert('1.0', demo)

    def _set_theme(self, name):
        self.values['--style'].set(name)
        if name in ('dark', 'tokyo-night'):
            self.out_text.configure(background='#1e1e2e', foreground='#ffffff')
        else:
            self.out_text.configure(background='#ffffff', foreground='#000000')

    def _save_plain(self):
        if not self.last_result or 'stdout' not in self.last_result:
            return
        f = filedialog.asksaveasfilename(defaultextension='.txt', filetypes=[('テキスト', '*.txt')])
        if not f:
            return
        if os.path.exists(f) and (not messagebox.askyesno('確認', '上書きしますか？')):
            return
        try:
            with open(f, 'w', encoding='utf-8') as fh:
                fh.write(runtime._strip_ansi(self.last_result['stdout'].decode('utf-8', 'replace')))
        except OSError as e:
            messagebox.showerror('保存エラー', str(e))

    def __init__(self, profile, source_dir):
        self._last_rendered_result = None
        super().__init__(profile, source_dir)
        self.out_text.configure(font=('Consolas', 11), background='#ffffff', foreground='#000000')
        self.in_text.master.configure(text='Markdownデータ（URL操作時はURL）')

    def _build_ui(self):
        super()._build_ui()
        self.tabs.pack_configure(expand=False)
        for tab in self.tabs.winfo_children():
            for child in tab.winfo_children():
                if isinstance(child, tk.Canvas):child.configure(height=110)
        self.path_list.master.configure(text='対象ファイル（ファイル操作で1つ選択）')
        for frame in self.path_list.master.winfo_children():
            for child in frame.winfo_children():
                if isinstance(child, ttk.Button) and child.cget('text')=='フォルダーを追加':child.pack_forget()
        ctrl = self.run_btn.master
        for child in ctrl.winfo_children():
            if isinstance(child, ttk.Button) and child.cget('text') == '結果を保存':
                child.configure(text='ANSIテキストを保存')
        demo_btn = ttk.Button(ctrl, text='デモ', command=self._load_demo)
        demo_btn.pack(side='left', padx=2)
        save_plain_btn = ttk.Button(ctrl, text='プレーン保存', command=self._save_plain)
        save_plain_btn.pack(side='left', padx=2)
        style_btn = ttk.Button(ctrl, text='スタイル選択(JSON)', command=self._choose_style)
        style_btn.pack(side='left', padx=2)
        theme_frame = ttk.Frame(self.root)
        theme_frame.pack(fill='x', padx=5, pady=2)
        ttk.Label(theme_frame, text='テーマ:').pack(side='left')
        for name in ['light', 'dark', 'ascii', 'tokyo-night', 'notty']:
            ttk.Button(theme_frame, text=name, command=lambda n=name: self._set_theme(n)).pack(side='left', padx=2)

    def _choose_style(self):
        f = filedialog.askopenfilename(filetypes=[('JSON', '*.json')])
        if f:
            self.values['--style'].set(f)

    def _worker(self, args, stdin_data, mode_def):
        try:
            if mode_def.get('files'):
                files = args[args.index('--') + 1:]
                if len(files) != 1 or not Path(files[0]).is_file() or os.path.getsize(files[0]) > 2 * 1024 * 1024:
                    raise ValueError('ファイル指定が不正です。')
                stdin_data = None
            elif mode_def.get('url'):
                url = stdin_data.decode().strip() if stdin_data else ''
                if not url or any((c.isspace() for c in url)):
                    raise ValueError('無効なURLです。')
                allowed_prefixes = ['https://', 'http://', 'github://', 'gitlab://', 'github.com/', 'gitlab.com/']
                if not any((url.startswith(p) for p in allowed_prefixes)):
                    raise ValueError('許可されないURLプレフィックスです。')
                args = [*args, '--', url]
                stdin_data = None
            super()._worker(args, stdin_data, mode_def)
        except Exception as e:
            self.q.put(('error', str(e)))

    def _poll_queue(self):
        super()._poll_queue()
        if self.last_result and 'stdout' in self.last_result and (self.last_result is not self._last_rendered_result):
            self._last_rendered_result = self.last_result
            try:
                raw = self.last_result['stdout'].decode('utf-8', 'replace')
                render_ansi(self.out_text, raw)
                if self.last_result.get('stderr'):
                    err = runtime._strip_ansi(self.last_result['stderr'][:MAX_RENDER].decode('utf-8', 'replace')).strip()
                    if err:
                        self.out_text.configure(state='normal')
                        self.out_text.insert('end', f'\n[stderr]\n{err}\n')
                        self.out_text.configure(state='disabled')
            except Exception as e:
                self.out_text.configure(state='normal')
                self.out_text.delete('1.0', 'end')
                self.out_text.insert('end', f'レンダリングエラー: {e}')
                self.status_var.set(f'表示エラー: {e}')
                self.out_text.configure(state='disabled')

def launch():
    profile_path = runtime.resource_path('profile.json', Path(__file__).resolve().parent)
    with open(profile_path, encoding='utf-8') as f:
        profile = json.load(f)
    app = MarkdownApp(profile, Path(__file__).resolve().parent)
    app.root.mainloop()
    return app
if __name__ == '__main__':
    launch()
