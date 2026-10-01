"""Subprocess runtime for the advanced CLI window.

Every execution uses a fixed bundled executable and an argument list. Output is
captured as bytes; GUI text decoding never changes the data available to save.
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

OSC_RE = re.compile(r'\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)')
ANSI_RE = re.compile(r'\x1b\[[0-?]*[ -/]*[@-~]|\x1b[@-_]')


def _strip_ansi(text: str) -> str:
    text = ANSI_RE.sub('', OSC_RE.sub('', text))
    return ''.join(c for c in text if c in '\n\t' or 32 <= ord(c) < 127 or ord(c) >= 160)


def resource_path(relative: str, source_dir: Path | None = None) -> str:
    base = Path(sys._MEIPASS) if getattr(sys, 'frozen', False) else source_dir or Path(__file__).parent
    return str(base / relative)


def build_command(exe, args, mandatory_args=(), blocked_flags=()):
    if not isinstance(args, list) or any(not isinstance(a, str) or '\x00' in a for a in args):
        raise ValueError('引数はNULを含まない文字列で指定してください。')
    if len(args) + len(mandatory_args) > 256:
        raise ValueError('引数は256個までです。')
    if sum(len(a.encode('utf-8')) for a in [*args,*mandatory_args]) > 64*1024:
        raise ValueError('引数は合計64 KiBまでです。')
    blocked={f.casefold() for f in blocked_flags}
    short={f[1] for f in blocked if len(f)==2 and f.startswith('-')}
    for arg in args:
        if arg == '--': break
        flag=arg.split('=',1)[0].casefold()
        if flag in blocked or any(b.endswith('-') and flag.startswith(b) for b in blocked):
            raise ValueError('このオプションは詳細機能では使用できません。')
        if arg.startswith('-') and not arg.startswith('--') and len(arg)>1:
            # Conservative rejection also covers attached values and short clusters.
            if any(ch.casefold() in short for ch in arg[1:]):
                raise ValueError('この短いオプションは使用できません。長い名前で指定してください。')
    tool=Path(exe).name.casefold()
    if tool=='pastel.exe' and 'pick' in args:
        raise ValueError('外部カラーピッカーは使用できません。')
    if tool=='fastfetch.exe' and any(a.casefold().startswith('--command-') for a in args):
        raise ValueError('外部コマンドを実行するモジュールは使用できません。')
    return [str(exe),*mandatory_args,*args]


def execute(exe, args, stdin_data=b'', cwd=None, cancel_event=None, timeout=300,
            max_output=16*1024*1024, mandatory_args=(), blocked_flags=()):
    cmd=build_command(exe,args,mandatory_args,blocked_flags)
    if not Path(exe).is_file():
        raise ValueError('同梱の実行ファイルが見つかりません。')
    if cwd is not None and not Path(cwd).is_dir():
        raise ValueError('作業フォルダーが見つかりません。')
    if not isinstance(stdin_data,bytes) or len(stdin_data)>2*1024*1024:
        raise ValueError('標準入力は2 MiBまでです。')
    if cancel_event and cancel_event.is_set(): raise InterruptedError('処理を停止しました。')
    env=os.environ.copy()
    for key in list(env):
        if key in ('RIPGREP_CONFIG_PATH','BAT_OPTS','BAT_PAGER','PAGER') or key.startswith(('DFT_','GITLEAKS_','XH_')):
            env.pop(key,None)
    with tempfile.TemporaryDirectory(prefix='kiwi-advanced-') as directory:
        folder=Path(directory)
        source,out,err=folder/'stdin.bin',folder/'stdout.bin',folder/'stderr.bin'
        source.write_bytes(stdin_data)
        config=folder/'config'; config.mkdir()
        env['XH_CONFIG_DIR']=str(config)
        with source.open('rb') as input_handle,out.open('wb') as output_handle,err.open('wb') as error_handle:
            proc=subprocess.Popen(cmd,stdin=input_handle,stdout=output_handle,stderr=error_handle,
                cwd=cwd,env=env,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
            try:
                deadline=time.monotonic()+timeout
                while proc.poll() is None:
                    if cancel_event and cancel_event.is_set(): raise InterruptedError('処理を停止しました。')
                    if time.monotonic()>deadline: raise TimeoutError('時間制限に達したため停止しました。')
                    if out.stat().st_size+err.stat().st_size>max_output:
                        raise ValueError('出力の上限に達したため停止しました。')
                    time.sleep(.03)
            finally:
                if proc.poll() is None: proc.kill()
                proc.wait()
        if cancel_event and cancel_event.is_set(): raise InterruptedError('処理を停止しました。')
        if out.stat().st_size+err.stat().st_size>max_output:
            raise ValueError('出力の上限を超えました。結果は保存しません。')
        return {'stdout':out.read_bytes(),'stderr':err.read_bytes(),'returncode':proc.returncode}
