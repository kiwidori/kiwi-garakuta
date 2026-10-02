import sys,json,tempfile,threading,subprocess
from decimal import Decimal
from pathlib import Path
from tkinter import ttk,filedialog,messagebox
import tkinter as tk
sys.path.insert(0,str(Path(__file__).resolve().parent.parent/'common'))
from workbench import App
import runtime
from ansi_renderer import render_ansi


def build_options(values):
    if values.get('--debug') and not values.get('--no-prelude'):
        raise ValueError('同梱Windows版は標準ライブラリとdebugの併用で異常終了します。「標準の単位・物理量を読み込まない」を有効にしてください。')
    args = []
    for k in ('--no-config', '--no-init', '--no-prelude', '--debug', '--inspect-interactively'):
        if values.get(k) is True:
            args.append(k)
    choices = {'--pretty-print': ('always', 'never', 'auto'), '--color': ('always', 'never', 'auto'), '--intro-banner': ('long', 'short', 'off')}
    defaults = {'--pretty-print': 'never', '--color': 'never', '--intro-banner': 'off'}
    for k, valid in choices.items():
        v = values.get(k, defaults[k])
        if v == '':
            continue
        if v not in valid:
            raise ValueError(f"Invalid value {v!r} for {k}")
        args.extend([k, v])
    return args


def _repl_data(values):
    if not values.get('--inspect-interactively'):return None
    data=(values.get('repl_commands','')+'\n').encode('utf8')
    if len(data)>2*1024*1024:raise ValueError('連続入力は2 MiBまでです。')
    return data

def checked_execute(exe,args,**kwargs):
    if len(subprocess.list2cmdline([str(exe),*args]))>=30000:raise ValueError('Windowsの引数長上限に達しました。追加式や引数を減らしてください。')
    result=runtime.execute(exe,args,blocked_flags=['--generate-config'],**kwargs)
    result['extension']='.txt'
    return result

def run_job(exe, values, mode, text, paths, cancel_event):
    if not isinstance(values, dict) or not isinstance(text, str) or not isinstance(paths, list):
        raise TypeError("invalid input types")
    if mode in ('プログラム', '連続入力・REPLコマンド') and len(text.encode('utf-8')) > 2 * 1024 * 1024:
        raise ValueError("text exceeds 2MiB limit")

    def _choice(key, default="auto"):
        v = values.get(key)
        if not isinstance(v, str):
            return default
        allowed = {"always", "never", "auto"} if key in ("--pretty-print", "--color") else {"long", "short", "off"}
        return v if v in allowed else default

    def _bool_flag(key):
        return bool(values.get(key))

    def _build_base_args():
        return build_options(values)

    def _expressions():
        raw = values.get("expressions")
        if not isinstance(raw, str):
            return []
        lines = [l.strip() for l in raw.splitlines()]
        exprs = [l for l in lines if l]
        if len(exprs) > 120:
            raise ValueError("too many expressions")
        joined = "\n".join(exprs)
        if len(joined.encode('utf-8')) > 12000:
            raise ValueError("expressions exceed limit")
        return exprs

    def _script_args():
        raw = values.get("script_args")
        if not isinstance(raw, str):
            return []
        args = [l for l in raw.splitlines() if l.strip()]
        if len(args) > 120:
            raise ValueError("too many script arguments")
        return args

    def _validate_conversion():
        num_s = values.get("number")
        src = values.get("source")
        tgt = values.get("target")
        if not isinstance(num_s, str) or not num_s.strip():
            raise ValueError("conversion number required")
        try:
            d = Decimal(num_s.strip())
        except Exception as e:
            raise ValueError(f"invalid decimal number: {e}") from None
        if not d.is_finite():
            raise ValueError("number must be finite")
        for name, val in (("source", src), ("target", tgt)):
            if not isinstance(val, str) or not val.strip() or any(c in val for c in ("\r", "\n", "\x00")):
                raise ValueError(f"{name} unit invalid")
        return d, src.strip(), tgt.strip()

    def _validate_file_mode():
        if len(paths) != 1:
            raise ValueError("exactly one file required")
        p = Path(paths[0])
        if not p.is_absolute():
            raise ValueError("file path must be absolute")
        if not p.exists() or not p.is_file():
            raise FileNotFoundError(f"script not found: {p}")
        return p

    def _validate_program_mode():
        if not text.strip():
            raise ValueError("program text is empty")

    def _validate_repl_mode():
        if not text.strip():
            raise ValueError("REPL input is empty")

    if mode == "ヘルプ":
        args = ["--help"]
        stdin_data = None
        cwd = None
    elif mode == "バージョン":
        args = ["--version"]
        stdin_data = None
        cwd = None
    elif mode == "単位変換":
        num, src, tgt = _validate_conversion()
        code = f"({num} {src}) -> {tgt}"
        args = _build_base_args() + ["-e", code]
        stdin_data = _repl_data(values)
        cwd = None
    elif mode == "プログラム":
        _validate_program_mode()
        exprs = _expressions()
        with tempfile.TemporaryDirectory(suffix=".nbt") as tmpdir:
            tmp_path = Path(tmpdir) / "program.nbt"
            tmp_path.write_text(text, encoding="utf-8")
            args = _build_base_args()
            for e in exprs:
                args += ["-e", e]
            args.append(str(tmp_path))
            args.extend(_script_args())
            result = checked_execute(exe, args, stdin_data=_repl_data(values), cwd=tmpdir, cancel_event=cancel_event)
        return result
    elif mode == "スクリプト":
        p = _validate_file_mode()
        exprs = _expressions()
        sargs = _script_args()
        args = _build_base_args()
        for e in exprs:
            args += ["-e", e]
        args.append(str(p))
        args.extend(sargs)
        stdin_data = _repl_data(values)
        cwd = str(p.parent)
    elif mode == "連続入力・REPLコマンド":
        _validate_repl_mode()
        args = _build_base_args()
        stdin_data = (text + "\n").encode("utf-8")
        cwd = None
    else:
        raise ValueError(f"invalid mode: {mode}")

    if mode in ("プログラム",):
        return result

    return checked_execute(exe, args, stdin_data=stdin_data, cwd=cwd, cancel_event=cancel_event)

CONFIG_TEMPLATE='''# Numbat v1.24.0 default config template, exported to a user-chosen path.
intro-banner = "long"
prompt = ">>> "
pretty-print = "auto"
color = "auto"
edit-mode = "emacs"
[formatting]
digit-separator = "_"
digit-grouping-threshold = 6
significant-digits = 6
datetime = "%Y-%m-%d %H:%M:%S"
[exchange-rates]
fetching-policy = "on-startup"
'''
SAMPLES={
 '距離・速度':'print(1 km -> m)\n100 km/h -> m/s',
 '変数と関数':'let distance = 12 km\nlet duration = 45 min\nfn speed(d: Length, t: Time) -> Velocity = d / t\nspeed(distance, duration) -> km/h',
 '統計':'use math::statistics\nprint(mean([2, 4, 6, 8]))\nmedian([1, 3, 7])',
 '数学':'print(sin(30 deg))\nprint(sqrt(9 m²))\nlog10(1000)',
 '温度':'25 °C -> °F',
 '日時':'use datetime::functions\nformat_datetime("%Y-%m-%d", datetime("2026-01-01 00:00 +0000"))',
 '方程式':'use numerics::solve\nfn f(x) = x² - 4\nroot_bisect(f, 1, 3, 0.001, 0.001)',
 '一覧と詳細':'list units\ninfo sin\nquit',
}

class CalcApp(App):
    def __init__(self,profile,source_dir):
        self._rendered=None
        super().__init__(profile,source_dir)

    def _build_ui(self):
        super()._build_ui()
        self.tabs.pack_configure(expand=False)
        for name in self.tabs.tabs():
            for child in self.tabs.nametowidget(name).winfo_children():
                if isinstance(child,tk.Canvas):child.configure(height=185)
        self.in_text.master.configure(text='プログラム / 連続入力（スクリプト後の入力は「追加式・引数」タブへ）')
        self.path_list.master.configure(text='スクリプトファイル（1つ選択、変換・プログラムでは無視）')
        for row in self.path_list.master.winfo_children():
            for button in row.winfo_children():
                if isinstance(button,ttk.Button) and button.cget('text')=='フォルダーを追加':button.destroy()
        self.out_text.configure(font=('Consolas',11),background='#111827',foreground='#f8fafc',wrap='none')
        row=ttk.Frame(self.root);row.pack(fill='x',before=self.tabs,padx=5,pady=3)
        ttk.Label(row,text='計算例:').pack(side='left')
        self.sample_var=tk.StringVar(value='変数と関数')
        ttk.Combobox(row,textvariable=self.sample_var,values=list(SAMPLES),state='readonly',width=17).pack(side='left')
        ttk.Button(row,text='例を入力',command=self._sample).pack(side='left',padx=3)
        ttk.Button(row,text='式を保存',command=self._save_program).pack(side='left',padx=3)
        ttk.Button(row,text='設定テンプレート',command=self._config).pack(side='left',padx=3)
        ttk.Label(row,text='各実行で計算状態をリセット。通貨/REPLは通信、show()はブラウザ起動。').pack(side='left',padx=5)

    def _sample(self):
        if self.worker and self.worker.is_alive():return
        name=self.sample_var.get();self._clear_paths()
        self.mode_var.set('連続入力・REPLコマンド' if name=='一覧と詳細' else 'プログラム')
        self.in_text.delete('1.0','end');self.in_text.insert('1.0',SAMPLES[name])
        for f in self.profile['fields']:
            self.values[f['flag']].set(f.get('default',''))
        for widget in self.repeat_widgets.values():widget.delete('1.0','end')

    def _save_program(self):
        text=self.in_text.get('1.0','end-1c')
        if len(text.encode('utf8'))>2*1024*1024:messagebox.showerror('保存','入力は2 MiBまでです。');return
        name=filedialog.asksaveasfilename(defaultextension='.nbt',filetypes=[('Numbat','*.nbt')])
        if not name:return
        if Path(name).exists() and not messagebox.askyesno('確認','上書きしますか？'):return
        try:Path(name).write_bytes(text.encode('utf8'))
        except OSError as e:messagebox.showerror('保存エラー',str(e))

    def _config(self):
        if self.worker and self.worker.is_alive():return
        self.last_result=dict(stdout=CONFIG_TEMPLATE.encode('utf8'),stderr=b'',returncode=0,extension='.toml')
        render_ansi(self.out_text,CONFIG_TEMPLATE);self.status_var.set('テンプレートを表示。「結果を保存」で任意先に保存できます。')

    def run(self):
        if self.worker and self.worker.is_alive():return
        values={key:value.get() for key,value in self.values.items()}
        for key,widget in self.repeat_widgets.items():values[key]=widget.get('1.0','end-1c')
        text=self.in_text.get('1.0','end-1c');mode=self.mode_var.get();paths=list(self.paths)
        self.last_result=None;self.cancel_event.clear();self.status_var.set('実行中…')
        self.run_btn.configure(state='disabled');self.stop_btn.configure(state='normal')
        self.worker=threading.Thread(target=self._job,args=(values,mode,text,paths),daemon=True);self.worker.start()

    def _job(self,values,mode,text,paths):
        try:
            result=run_job(self.exe_path,values,mode,text,paths,self.cancel_event)
            rc=result['returncode'];self.q.put(('done',rc,result['stdout'],result['stderr'],rc==0,result))
        except Exception as error:self.q.put(('error',str(error)))

    def _poll_queue(self):
        super()._poll_queue()
        r=self.last_result
        if r is not None and r is not self._rendered and 'stdout' in r:
            self._rendered=r;text=r['stdout'].decode('utf8','replace')
            if r.get('stderr'):text+='\n'+r['stderr'].decode('utf8','replace')
            render_ansi(self.out_text,text)

if __name__=='__main__':
    source=Path(__file__).resolve().parent
    profile=json.loads(Path(runtime.resource_path('profile.json',source)).read_text(encoding='utf8'))
    CalcApp(profile,source).root.mainloop()
