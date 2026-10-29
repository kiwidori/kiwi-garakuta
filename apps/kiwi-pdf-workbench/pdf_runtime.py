"""Run the PDF DLL host with an in-memory job and no command-line secrets."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
from consumer_runtime import NativeJob


def resource_path(relative, source_dir=None):
    base = Path(sys._MEIPASS) if getattr(sys, 'frozen', False) else source_dir or Path(__file__).parent
    return str(base / relative)


def execute(exe, args, stdin_data=b'', cwd=None, cancel_event=None, timeout=300, max_output=16*1024**2):
    if args or Path(exe).name != 'KiwiPdfHost.exe' or not Path(exe).is_file():
        raise ValueError('PDFエンジンを確認できません。')
    if not isinstance(stdin_data, bytes) or len(stdin_data) > 2*1024**2:
        raise ValueError('処理設定は2 MiBまでです。')
    if cancel_event and cancel_event.is_set():
        raise InterruptedError('停止しました。')
    with tempfile.TemporaryDirectory(prefix='kiwi-pdf-log-') as td:
        out, err = Path(td)/'stdout', Path(td)/'stderr'
        with out.open('wb') as stdout, err.open('wb') as stderr:
            group = NativeJob()
            try:
                proc = subprocess.Popen([str(exe)], stdin=subprocess.PIPE, stdout=stdout, stderr=stderr,
                                        cwd=cwd, creationflags=subprocess.CREATE_NO_WINDOW)
                group.attach(proc)
            except BaseException:
                group.close()
                raise
            def feed():
                try:
                    proc.stdin.write(stdin_data)
                except (BrokenPipeError, OSError):
                    pass
                finally:
                    try:
                        proc.stdin.close()
                    except (BrokenPipeError, OSError):
                        pass
            writer = threading.Thread(target=feed, daemon=True)
            writer.start()
            deadline = time.monotonic()+timeout
            try:
                while proc.poll() is None:
                    if cancel_event and cancel_event.is_set():
                        raise InterruptedError('停止しました。')
                    if time.monotonic() > deadline:
                        raise TimeoutError('処理の時間制限を超えました。')
                    if out.stat().st_size + err.stat().st_size > max_output:
                        raise ValueError('ログが大きすぎます。')
                    time.sleep(.03)
            finally:
                group.close()
                proc.wait(timeout=10)
                writer.join(timeout=2)
        if cancel_event and cancel_event.is_set():
            raise InterruptedError('停止しました。')
        if out.stat().st_size + err.stat().st_size > max_output:
            raise ValueError('ログが大きすぎます。')
        return {'stdout': out.read_bytes(), 'stderr': err.read_bytes(), 'returncode': proc.returncode}
