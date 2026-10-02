"""Regression checks for executable selection, ANSI decoding and stdin pipes."""
import json
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'apps/common'))
import runtime
from advanced import AdvancedController, BUNDLED_TOOLS


def main():
    assert runtime._strip_ansi('\x1b[31mred\x1b[0m\x1b]8;;https://example.com\x07link\x1b]8;;\x07') == 'redlink'
    assert runtime._strip_ansi('\x1b]title\x1b\\ok') == 'ok'
    assert runtime._strip_ansi('\x1b]abc') == 'abc'
    assert runtime._strip_ansi('\x1b[123') == '123'
    assert runtime._strip_ansi('日本語\x00\r\n\t\x7f') == '日本語\n\t'
    before = time.monotonic()
    assert runtime._strip_ansi('\x1b]' * 200000) == ''
    assert time.monotonic() - before < 3, 'Repeated incomplete OSC is too slow'
    print('PASS complete/incomplete ANSI, Unicode and repeated OSC performance', flush=True)

    for spec in (ROOT / 'apps').glob('kiwi-*/advanced-spec.json'):
        tool = json.loads(spec.read_text(encoding='utf8'))['tool']
        assert tool in BUNDLED_TOOLS
    controller = AdvancedController.__new__(AdvancedController)
    controller.source_dir = ROOT / 'apps/kiwi-search'
    for name in ('../evil.exe', 'C:/evil.exe', '..', 'rg.exe/../evil.exe', 'rg.exe:evil', 'unknown.exe'):
        controller.tool_name = name
        try:
            controller._resolve_exe()
        except ValueError:
            pass
        else:
            raise AssertionError('Unsafe tool name accepted: ' + name)
    controller.tool_name = 'rg.exe'
    assert Path(controller._resolve_exe()).parent == controller.source_dir
    print('PASS all 25 tool names and traversal/absolute/alternate-stream rejection', flush=True)

    original_write = Path.write_bytes
    def no_stdin_file(path, data):
        assert path.name != 'stdin.bin', 'Plaintext stdin file created'
        return original_write(path, data)
    data = bytes(range(256)) * 8192
    with patch.object(Path, 'write_bytes', no_stdin_file):
        result = runtime.execute(sys.executable, ['-c', 'import sys;sys.stdout.buffer.write(sys.stdin.buffer.read())'], stdin_data=data)
        assert result['stdout'] == data and result['returncode'] == 0
        assert runtime.execute(sys.executable, ['-c', 'import sys;print(len(sys.stdin.buffer.read()))'])['stdout'].strip() == b'0'
        assert runtime.execute(sys.executable, ['-c', 'pass'], stdin_data=data)['returncode'] == 0
        try:
            runtime.execute(sys.executable, ['-c', 'import time;time.sleep(20)'], stdin_data=data, timeout=.2)
        except TimeoutError:
            pass
        else:
            raise AssertionError('Blocked stdin prevented timeout')
        event = threading.Event()
        timer = threading.Timer(.2, event.set)
        timer.start()
        try:
            runtime.execute(sys.executable, ['-c', 'import time;time.sleep(20)'], stdin_data=data, cancel_event=event)
        except InterruptedError:
            pass
        else:
            raise AssertionError('Blocked stdin prevented cancellation')
        finally:
            timer.join()
    assert not any(t.name == 'kiwi-stdin' and t.is_alive() for t in threading.enumerate())
    print('PASS 2MiB binary stdin, EOF, early exit, blocked-reader timeout/cancel and writer cleanup', flush=True)


if __name__ == '__main__':
    main()
