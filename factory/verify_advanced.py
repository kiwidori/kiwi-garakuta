"""Exercise the shared runner with actual Windows CLI binaries and real inputs."""
from __future__ import annotations
import argparse
import http.server
import importlib.util
import json
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'apps/common'))
from runtime import execute,build_command,_strip_ansi

TOOLS={
 'kiwi-search':'rg.exe','kiwi-find':'fd.exe','kiwi-disk':'dust.exe','kiwi-json':'jq.exe',
 'kiwi-code':'bat.exe','kiwi-system':'fastfetch/fastfetch.exe','kiwi-secrets':'gitleaks.exe',
 'kiwi-regex':'grex/grex.exe','kiwi-http':'xh/xh-v0.26.2-x86_64-pc-windows-msvc/xh.exe',
 'kiwi-png':'oxipng/oxipng-10.2.1-x86_64-pc-windows-msvc/oxipng.exe','kiwi-yaml':'yq/yq.exe',
 'kiwi-hash':'b3sum.exe','kiwi-color':'pastel/pastel-v0.12.0-x86_64-pc-windows-msvc/pastel.exe',
 'kiwi-ascii':'ascii/ascii-image-converter_Windows_amd64_64bit/ascii-image-converter.exe',
 'kiwi-space':'duf/duf.exe','kiwi-diff':'difft/difft.exe',
}

def runtime_tests():
    for args,blocked in [(['--redact=0'],['--redact']),(['-xwhoami'],['-x']),(['-HIx','whoami'],['-x']),(['--CONFIG=bad'],['--config'])]:
        try: build_command('tool.exe',args,blocked_flags=blocked)
        except ValueError: pass
        else: raise AssertionError('blocked flag accepted')
    assert build_command('tool.exe',['--','--redact=0'],['--redact=100'],['--redact']) == ['tool.exe','--redact=100','--','--redact=0']
    assert _strip_ansi('\x1b[31mred\x1b[0m\x1b]8;;https://example.com\x07link\x1b]8;;\x07')=='redlink'
    with tempfile.TemporaryDirectory() as temp:
        folder=Path(temp)
        event=threading.Event()
        slow=folder/'slow.py'; slow.write_text('import time; time.sleep(30)',encoding='utf8')
        try: execute(sys.executable,[str(slow)],cwd=temp,timeout=.1)
        except TimeoutError: pass
        else: raise AssertionError('timeout ignored')
        timer=threading.Timer(.1,event.set);timer.start()
        try: execute(sys.executable,[str(slow)],cwd=temp,cancel_event=event)
        except InterruptedError: pass
        else: raise AssertionError('cancellation ignored')
        finally: timer.join()
        loud=folder/'loud.py';loud.write_text("import sys; sys.stdout.buffer.write(b'a'*200000)",encoding='utf8')
        try: execute(sys.executable,[str(loud)],max_output=1024)
        except ValueError: pass
        else: raise AssertionError('finished output limit ignored')
        binary=folder/'binary.py';binary.write_text("import sys; sys.stdout.buffer.write(bytes(range(256)))",encoding='utf8')
        assert execute(sys.executable,[str(binary)])['stdout']==bytes(range(256))
    print('PASS: flag validation, ANSI, timeout, cancellation, output cap, binary bytes')

def upstream_tests():
    # This fixture is kept separately so the public verifier has no private paths.
    fixture_path=ROOT/'factory/advanced_fixtures.py'
    module=importlib.util.spec_from_file_location('advanced_cases',fixture_path)
    cases=importlib.util.module_from_spec(module);module.loader.exec_module(cases)
    for slug,(args,data,predicate) in cases.CASES.items():
        spec=json.loads((ROOT/'apps'/slug/'advanced-spec.json').read_text(encoding='utf8'))
        result=execute(ROOT/'.tools'/TOOLS[slug],args,stdin_data=data,cwd=cases.PUBLIC,
            mandatory_args=spec['mandatory_args'],blocked_flags=spec['blocked_flags'])
        assert result['returncode']==0,(slug,result['stderr'][:300])
        assert predicate(result['stdout']),slug
        print('PASS:',slug,'added operation via shared runner')
        for example in spec['examples']:
            result=execute(ROOT/'.tools'/TOOLS[slug],example['args'],stdin_data=example['stdin'].encode(),cwd=cases.PUBLIC,
                mandatory_args=spec['mandatory_args'],blocked_flags=spec['blocked_flags'])
            assert result['returncode']==0,(slug,example['name'],result['stderr'][:200])
    secret=('ghp_'+'AbCdEf123456'*3).encode()
    spec=json.loads((ROOT/'apps/kiwi-secrets/advanced-spec.json').read_text(encoding='utf8'))
    report=execute(ROOT/'.tools'/TOOLS['kiwi-secrets'],['stdin','--report-format','json','--report-path','-'],
        stdin_data=b'token="'+secret+b'"\n',mandatory_args=spec['mandatory_args'],blocked_flags=spec['blocked_flags'])
    assert report['returncode']==1 and json.loads(report['stdout']), 'synthetic secret was not detected'
    assert secret not in report['stdout']+report['stderr'], 'gitleaks did not redact synthetic secret'
    print('PASS: synthetic Gitleaks detection is fully redacted')
    class Handler(http.server.BaseHTTPRequestHandler):
        def do_POST(self):
            data=self.rfile.read(int(self.headers.get('Content-Length','0')))
            self.send_response(200); self.end_headers();self.wfile.write(data)
        def log_message(self,*args): pass
    server=http.server.ThreadingHTTPServer(('127.0.0.1',0),Handler)
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    try:
        spec=json.loads((ROOT/'apps/kiwi-http/advanced-spec.json').read_text(encoding='utf8'))
        result=execute(ROOT/'.tools'/TOOLS['kiwi-http'],['--pretty=none','--print=b','POST',f'http://127.0.0.1:{server.server_port}/','X-Demo:kiwi'],stdin_data=b'{"name":"kiwi"}',mandatory_args=spec['mandatory_args'])
        assert result['returncode']==0 and b'kiwi' in result['stdout'],result['stderr']
        print('PASS: real POST body and header to loopback HTTP server')
    finally: server.shutdown();server.server_close();thread.join()

if __name__=='__main__':
    runtime_tests()
    upstream_tests()
