import os
import re
import time
import shutil
import tempfile
import threading
import subprocess
from pathlib import Path

_ANSI_RE = re.compile(r'\x1b\[[0-9;]*[A-Za-z]')


def run_native(exe, args, secret, cwd, cancel, timeout=3600, relay_password=""):
    exe = Path(exe).resolve()
    if not exe.is_file():
        raise RuntimeError("executable not found")

    private_dir = Path(tempfile.mkdtemp(prefix="croc_priv_"))
    try:
        env = os.environ.copy()
        for k in list(env.keys()):
            if k.upper().startswith("CROC_") or k.upper() in ("SOCKS5_PROXY", "HTTP_PROXY", "HTTPS_PROXY"):
                del env[k]
        for proxy_key in ("SOCKS5_PROXY", "HTTP_PROXY", "HTTPS_PROXY"):
            env.pop(proxy_key, None)

        env["CROC_SECRET"] = secret
        if relay_password:
            env["CROC_PASS"] = relay_password
        env["USERPROFILE"] = str(private_dir)
        env["HOME"] = str(private_dir)
        env["APPDATA"] = str(private_dir / "AppData" / "Roaming")
        env["LOCALAPPDATA"] = str(private_dir / "AppData" / "Local")
        env["XDG_CONFIG_HOME"] = str(private_dir / ".config")

        for sub in ("AppData/Roaming", "AppData/Local", ".config"):
            (private_dir / sub).mkdir(parents=True, exist_ok=True)

        cmd = [str(exe)] + list(args)
        proc = subprocess.Popen(
            cmd,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            cwd=str(cwd),
            env=env,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )

        buf = bytearray()
        limit_hit = False
        max_bytes = 4 * 1024 * 1024

        def reader():
            nonlocal limit_hit
            try:
                while True:
                    chunk = proc.stdout.read(65536)
                    if not chunk:
                        break
                    remaining = max_bytes - len(buf)
                    buf.extend(chunk[:max(0, remaining)])
                    if len(chunk) > remaining and not limit_hit:
                        limit_hit = True
                        try:
                            proc.kill()
                        except OSError:
                            pass
            except Exception:
                pass

        t_reader = threading.Thread(target=reader, daemon=True)
        t_reader.start()

        start = time.monotonic()
        status = "ok"
        while proc.poll() is None:
            if cancel.is_set():
                status = "cancel"
                break
            if (time.monotonic() - start) > timeout:
                status = "timeout"
                break
            time.sleep(0.1)

        try:
            if proc.poll() is None:
                proc.kill()
            proc.wait(timeout=5)
        except Exception:
            pass
        finally:
            t_reader.join(timeout=2)

        raw = bytes(buf).decode("utf-8", errors="replace")
        clean = _ANSI_RE.sub("", raw)
        if secret:
            clean = clean.replace(secret, "[共有コード]")
        if relay_password:
            clean = clean.replace(relay_password, "[リレーパスワード]")
        clean = re.sub(r'(?m)^On the other computer, run:\s*\n\s*croc[^\n]*\n?', '', clean)
        clean = re.sub(r'(?m)^Or open:\s*\n\s*https?://[^\n]*\n?', '', clean)
        clean = re.sub(r'(?<![\w.])(?:\d{1,3}\.){3}\d{1,3}(?![\w.])', '[接続先]', clean)

        if status != "ok":
            raise RuntimeError("転送を停止しました。" if status == "cancel" else "1時間以内に転送が完了しませんでした。")

        if limit_hit:
            raise RuntimeError("表示データが4 MiBを超えたため停止しました。")

        if proc.returncode != 0:
            tail = clean[-3000:]
            raise RuntimeError(tail)

        return clean.strip()
    finally:
        shutil.rmtree(private_dir, ignore_errors=True)
