"""Run the bundled jq with bounded shared query inputs."""
import tempfile, time, runtime
from structured import query_job

def execute_job(exe, mode, values, paths, text, cancel_event):
    deadline = time.monotonic() + 300
    if cancel_event.is_set(): raise InterruptedError
    if mode=='query':
        if values.get('@input')=='yaml' or values.get('@output')=='yaml':raise ValueError('jqはYAML入出力に対応しません。gojqを選んでください。')
        raw=values.get('--indent','')
        if str(raw).strip():
            try:ind=int(str(raw))
            except (TypeError,ValueError):raise ValueError('字下げの幅は0〜7の整数で指定してください。') from None
            if not 0<=ind<=7:raise ValueError('字下げの幅は0〜7の整数で指定してください。')
    args, stdin, extension = query_job.build_request(mode, values, paths, text)
    for f in ['--sort-keys','--ascii-output','--seq','--stream-errors','--binary']:
        if mode=='query' and values.get(f): args.insert(0, f)
    with tempfile.TemporaryDirectory() as td:
        now = time.monotonic()
        if cancel_event.is_set(): raise InterruptedError
        result = runtime.execute(exe, args, stdin_data=stdin, cwd=td, cancel_event=cancel_event, timeout=max(.1, deadline - now), max_output=16777216)
    if time.monotonic() > deadline: raise TimeoutError
    result['extension'] = extension
    result['display'] = runtime._strip_ansi(result['stdout'].decode('utf8','replace'))[:131072]
    return result
