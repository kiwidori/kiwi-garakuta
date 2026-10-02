import sys,json,subprocess,tempfile,tomllib,os,re,math
from pathlib import Path
from tkinter import ttk,filedialog,messagebox
import tkinter as tk
sys.path.insert(0,str(Path(__file__).resolve().parent.parent/'common'))
from workbench import App
import runtime
from ansi_renderer import render_ansi
import templates


def normalize_branch_args(args):
    mapping = {'--diff-from': ('diff', 'from'), '--diff-to': ('diff', 'to'),
               '--log-from': ('log', 'from'), '--log-to': ('log', 'to')}
    try:
        sep_idx = args.index('--')
    except ValueError:
        before, suffix = list(args), []
    else:
        before, suffix = list(args[:sep_idx]), list(args[sep_idx:])
    out, pending, seen = [], None, {}
    for tok in before:
        if pending is not None:
            if tok == '--' or tok in mapping or tok.startswith('--'):
                raise ValueError(f"missing value for {pending}")
            if not tok:
                raise ValueError("empty branch value")
            group, key = mapping[pending]
            seen.setdefault(group, {})[key] = tok
            pending = None
        elif tok in mapping:
            if tok in seen:
                raise ValueError(f"duplicate {tok}")
            group, key = mapping[tok]
            if key in seen.get(group, {}):
                raise ValueError(f"duplicate {group} {key}")
            seen.setdefault(group, {})[key] = None
            pending = tok
        else:
            out.append(tok)
    if pending is not None:
        raise ValueError(f"missing value for {pending}")
    for group in ('diff', 'log'):
        vals = seen.get(group, {})
        if len(vals) == 1:
            raise ValueError(f"incomplete --{group}-from/--{group}-to pair")
        if len(vals) == 2:
            out.extend(['--git-' + group + '-branch', vals['from'], vals['to']])
    return out + suffix


def extend_template(template, fmt):
    if fmt == 'markdown':
        return template + '\n{{#if git_diff_branch}}\nGit Branch Diff:\n{{{git_diff_branch}}}\n{{/if}}\n{{#if git_log_branch}}\nGit Branch Log:\n{{{git_log_branch}}}\n{{/if}}\n'
    if fmt in ('xml', 'json'):
        return template + '\n{{#if git_diff_branch}}<git-branch-diff>{{git_diff_branch}}</git-branch-diff>{{/if}}\n{{#if git_log_branch}}<git-branch-log>{{git_log_branch}}</git-branch-log>{{/if}}\n'
    raise ValueError(f"Unsupported format: {fmt}")


import re

def prepare_template(text, variables):
    """
    Prepare a template string by resolving built-in variables to 'this.<name>' references
    and validating user-defined variables against the provided dictionary.

    Args:
        text (str): The template string containing {{variable}} or {{{variable}}} placeholders.
        variables (dict): A dictionary of user-defined variable names to their values.

    Returns:
        str: The processed template string with built-ins rewritten and user variables validated.

    Raises:
        ValueError: If a simple bare name is found that is neither a builtin nor in the variables dict.
    """
    # Builtin set as specified
    builtins = {
        'absolute_code_path', 'source_tree', 'files', 'path', 'code',
        'git_diff', 'git_diff_branch', 'git_log_branch', 'token_count',
        'language', 'extension'
    }

    # Pattern to match {{name}}, {{{name}}}, etc.
    # Group 1: Opening braces ({{ or {{{)
    # Group 2: Variable name
    # Group 3: Closing braces (}} or }}})
    pattern = r'(\{\{+?)\s*([A-Za-z_][A-Za-z_0-9]*)\s*(\}\}+?)'

    def replace_match(match):
        opening = match.group(1)
        name = match.group(2)
        closing = match.group(3)
        if name == 'else':return match.group(0)

        # If it's a builtin, rewrite to {{this.name}} preserving brace count
        if name in builtins:
            return f"{opening}this.{name}{closing}"

        # If it's in the user variables dict, leave unchanged (it will be resolved by Handlebars context)
        if name in variables:
            return match.group(0)

        # Otherwise, raise an error for missing template variable
        raise ValueError(f"Missing template variable: {name}")

    # Use re.sub to replace all matches
    result = re.sub(pattern, replace_match, text)

    return result


def process(exe,args,stdin_data,mode_def,cancel_event):
    mandatory=['--output-file','-']
    blocked=['--tui','--clipboard-daemon','--clipboard','-c','--output-file','-O']
    info=not mode_def.get('files')
    cwd=None
    final_args=list(args)
    variable_input={}
    if not info and '--template-vars' in final_args:
        index=final_args.index('--template-vars')
        if index+1>=len(final_args):raise ValueError('テンプレート変数のJSONがありません。')
        variable_input=json.loads(final_args[index+1])
        if not isinstance(variable_input,dict) or any(not isinstance(k,str) or not isinstance(v,str) for k,v in variable_input.items()):raise ValueError('変数は文字列キーと文字列値のJSONオブジェクトにしてください。')
        final_args=final_args[:index]+final_args[index+2:]
    if not info:final_args=normalize_branch_args(final_args)
    if not info:
        if '--' not in final_args:raise ValueError('対象フォルダーを選択してください。')
        post=final_args[final_args.index('--')+1:]
        if len(post)!=1 or not Path(post[0]).is_dir():raise ValueError('既存フォルダーを1つ選択してください。')
        cwd=str(Path(post[0]).absolute())
    if len(subprocess.list2cmdline([str(exe),*mandatory,*final_args]))>=30000:raise ValueError('Windowsの引数長上限に達しました。')
    pre=final_args[:final_args.index('--')] if '--' in final_args else final_args
    fmt=pre[pre.index('--output-format')+1] if '--output-format' in pre else 'markdown'
    if not info:
        config={}
        for config_path in (Path(cwd)/'.c2pconfig',Path(os.getenv('APPDATA',''))/'code2prompt'/'.c2pconfig'):
            if config_path.is_file():
                if config_path.stat().st_size>2*1024*1024:raise ValueError('設定ファイルは2 MiBまでです。')
                try:config=tomllib.loads(config_path.read_text(encoding='utf8'))
                except (ValueError,UnicodeError):continue
                break
        variables=dict(config.get('user_variables',{}));variables.update(variable_input)
        variables.setdefault('else','')
        if any(not isinstance(k,str) or not isinstance(v,str) for k,v in variables.items()):raise ValueError('設定のテンプレート変数は文字列にしてください。')
        config['user_variables']=variables
        if '--template' in pre:
            index=final_args.index('--template');original=Path(final_args[index+1]);original=original if original.is_absolute() else Path(cwd)/original
            if original.stat().st_size>2*1024*1024:raise ValueError('テンプレートは2 MiBまでです。')
            template=original.read_text(encoding='utf8');final_args=final_args[:index]+final_args[index+2:]
        elif config.get('template_str'):
            template=config['template_str']
        else:
            template=templates.MARKDOWN if fmt=='markdown' else templates.XML
            if any(flag in pre for flag in ('--git-diff-branch','--git-log-branch')):template=extend_template(template,fmt)
        template=prepare_template(template,variables)
        with tempfile.TemporaryDirectory(prefix='kiwi-prompt-config-') as td:
            path=Path(td)/'template.hbs';path.write_text(template,encoding='utf8')
            cfg='\n'.join(json.dumps(k,ensure_ascii=False)+' = '+toml_value(v) for k,v in config.items())+'\n'
            tomllib.loads(cfg)
            (Path(td)/'.c2pconfig').write_text(cfg,encoding='utf8')
            index=final_args.index('--');final_args=final_args[:index]+['--template',str(path)]+final_args[index:]
            if len(subprocess.list2cmdline([str(exe),*mandatory,*final_args]))>=30000:raise ValueError('Windowsの引数長上限に達しました。')
            result=runtime.execute(exe,final_args,stdin_data=None,cwd=td,cancel_event=cancel_event,mandatory_args=mandatory,blocked_flags=blocked)
    else:
        result=runtime.execute(exe,final_args,stdin_data=None,cwd=cwd,cancel_event=cancel_event,mandatory_args=mandatory,blocked_flags=blocked)
    result['extension']='.txt' if info else {'markdown':'.md','json':'.json','xml':'.xml'}.get(fmt,'.md')
    return result

def toml_value(value):
    if isinstance(value,str):return json.dumps(value,ensure_ascii=False)
    if isinstance(value,bool):return 'true' if value else 'false'
    if isinstance(value,int):return str(value)
    if isinstance(value,float) and math.isfinite(value):return repr(value)
    if isinstance(value,list):return '['+', '.join(toml_value(v) for v in value)+']'
    if isinstance(value,dict):return '{'+', '.join(json.dumps(k,ensure_ascii=False)+' = '+toml_value(v) for k,v in value.items())+'}'
    raise ValueError('設定ファイルに対応していない値があります。')

class PromptApp(App):
    def __init__(self,profile,source_dir):
        self._rendered=None
        super().__init__(profile,source_dir)
    def _build_ui(self):
        super()._build_ui();self.tabs.pack_configure(expand=False)
        for name in self.tabs.tabs():
            for child in self.tabs.nametowidget(name).winfo_children():
                if isinstance(child,tk.Canvas):child.configure(height=260)
        self.in_text.master.pack_forget()
        self.path_list.master.configure(text='コード資料にまとめるフォルダー（1つ選択）')
        for row in self.path_list.master.winfo_children():
            for button in row.winfo_children():
                if isinstance(button,ttk.Button) and button.cget('text')=='ファイルを追加':button.destroy()
        self.out_text.configure(font=('Consolas',11),background='#111827',foreground='#f8fafc',wrap='none')
        for title,callback in [('デモ',self._demo),('テンプレートを選択',self._template),('結果をコピー',self._copy),('診断・トークン情報を保存',self._save_diagnostics)]:
            ttk.Button(self.run_btn.master,text=title,command=callback).pack(side='left',padx=2)
    def _demo(self):
        if self.worker and self.worker.is_alive():return
        folder=Path('C:/Users/Public/Documents/kiwi-prompt-demo');folder.mkdir(parents=True,exist_ok=True)
        for name,text in [('hello.py','def hello(name):\n    return f"Hello, {name}!"\n'),('README.md','# Demo project\nA tiny example for code2prompt.\n')]:
            file=folder/name
            if not file.exists():file.write_text(text,encoding='utf8')
        self._clear_paths();self.paths=[str(folder)];self.path_list.insert('end',str(folder));self.mode_var.set('コード資料を生成')
        for field in self.profile['fields']:self.values[field['flag']].set(field.get('default',''))
        for widget in self.repeat_widgets.values():widget.delete('1.0','end')
    def _template(self):
        name=filedialog.askopenfilename(filetypes=[('Handlebars','*.hbs *.handlebars'),('All','*.*')])
        if name:self.values['--template'].set(name)
    def _copy(self):
        if not self.last_result or 'stdout' not in self.last_result:return
        try:
            text=self.last_result['stdout'].decode('utf8')
            self.root.clipboard_clear();self.root.clipboard_append(text);self.root.update_idletasks()
            self.status_var.set('標準出力をコピーしました。')
        except (tk.TclError,UnicodeError) as error:messagebox.showerror('コピー',str(error))
    def _save_diagnostics(self):
        if not self.last_result or 'stderr' not in self.last_result:return
        name=filedialog.asksaveasfilename(defaultextension='.log')
        if not name:return
        if Path(name).exists() and not messagebox.askyesno('確認','上書きしますか？'):return
        try:Path(name).write_bytes(self.last_result['stderr'])
        except OSError as error:messagebox.showerror('保存',str(error))
    def _poll_queue(self):
        super()._poll_queue();r=self.last_result
        if r is not None and r is not self._rendered and 'stdout' in r:
            self._rendered=r;text=r['stdout'].decode('utf8','replace')
            if r.get('stderr'):text+='\n--- 診断・トークン情報（標準エラー） ---\n'+r['stderr'].decode('utf8','replace')
            render_ansi(self.out_text,text)
    def _worker(self,args,stdin_data,mode_def):
        try:
            r=process(self.exe_path,args,stdin_data,mode_def,self.cancel_event);rc=r['returncode']
            self.q.put(('done',rc,r['stdout'],r['stderr'],rc==0,r))
        except Exception as error:self.q.put(('error',str(error)))

if __name__=='__main__':
    source=Path(__file__).resolve().parent
    profile=json.loads(Path(runtime.resource_path('profile.json',source)).read_text(encoding='utf8'))
    PromptApp(profile,source).root.mainloop()
