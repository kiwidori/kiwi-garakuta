"""Read-only fixed-expression yq conversion and exclusive result saving."""
import sys
import time
import tempfile
import subprocess
from pathlib import Path

MAX_INPUT=2*1024*1024
MAX_OUTPUT=4*1024*1024

def resource_dir():
    return Path(sys._MEIPASS) if getattr(sys,'frozen',False) else Path(__file__).resolve().parent

def convert(exe,source,mode,cancel):
    source=Path(source).resolve()
    if not source.is_file() or source.suffix.lower() not in ('.yml','.yaml'):
        raise ValueError('YAMLファイルを選んでください。')
    if mode not in ('yaml','json'):
        raise ValueError('整形またはJSON変換を選んでください。')
    if not exe.is_file():
        raise ValueError('同梱のyq.exeが見つかりません。')
    with source.open('rb') as stream:
        raw=stream.read(MAX_INPUT+1)
    if len(raw)>MAX_INPUT:
        raise ValueError('入力は2 MiBまでです。')
    try:
        text=raw.decode('utf-8-sig')
    except UnicodeError:
        raise ValueError('UTF-8のYAMLを選んでください。') from None
    if not text.strip():
        raise ValueError('入力ファイルが空です。')
    if cancel.is_set():
        raise InterruptedError()
    with tempfile.TemporaryDirectory(prefix='kiwi-yaml-') as temp:
        folder=Path(temp)
        input_path=folder/'input.yaml'
        out_path=folder/'result.bin'
        err_path=folder/'error.bin'
        input_path.write_text(text,encoding='utf-8')
        cmd=[str(exe.resolve()),'eval','--input-format=yaml',f'--output-format={mode}','--no-colors','--security-disable-env-ops','--security-disable-file-ops']
        if mode=='yaml':
            cmd.append('--prettyPrint')
        cmd+=['.',str(input_path)]
        with out_path.open('wb') as out,err_path.open('wb') as err:
            proc=subprocess.Popen(cmd,stdin=subprocess.DEVNULL,stdout=out,stderr=err,cwd=temp,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
            try:
                deadline=time.monotonic()+15
                while proc.poll() is None:
                    if cancel.is_set():
                        raise InterruptedError()
                    if time.monotonic()>deadline:
                        raise TimeoutError()
                    if out_path.stat().st_size>MAX_OUTPUT or err_path.stat().st_size>65536:
                        raise ValueError('処理結果が上限を超えたため停止しました。')
                    time.sleep(0.05)
            finally:
                if proc.poll() is None:
                    proc.kill()
                proc.wait()
        if cancel.is_set():
            raise InterruptedError()
        if proc.returncode!=0:
            raise ValueError('変換に失敗しました。YAMLの構文や対応形式を確認してください。')
        if out_path.stat().st_size>MAX_OUTPUT:
            raise ValueError('結果は4 MiBまでです。')
        return out_path.read_bytes().decode('utf-8')

def save_result(text,source,destination):
    destination=Path(destination).resolve()
    if destination==Path(source).resolve():
        raise ValueError('元ファイルと異なる保存先を選んでください。')
    data=text.encode('utf-8')
    if len(data)>MAX_OUTPUT:
        raise ValueError('結果は4 MiBまでです。')
    try:
        stream=destination.open('xb')
    except FileExistsError:
        raise ValueError('既存ファイルには上書きできません。別の名前を選んでください。') from None
    try:
        with stream:
            stream.write(data)
    except Exception:
        destination.unlink(missing_ok=True)
        raise
