import json
import os
import subprocess
import tempfile
import threading
import time
from pathlib import Path


def local_repository(value, must_exist=True):
    if not isinstance(value, str) or not value:
        raise ValueError("リポジトリパスは空でない文字列である必要があります")
    if "\x00" in value or "\r" in value or "\n" in value:
        raise ValueError("リポジトリパスに無効な制御文字が含まれています")
    if "://" in value:
        raise ValueError("URLスキームまたはリモートバックエンドはサポートされていません")
    p = Path(value)
    if not p.is_absolute():
        raise ValueError("リポジトリパスは絶対パスである必要があります")
    try:
        resolved = p.resolve()
    except OSError as e:
        raise ValueError(f"リポジトリパスを解決できません: {e}") from e
    if must_exist and not resolved.exists():
        raise FileNotFoundError("リポジトリが存在しません。先に初期化してください")
    if resolved.exists() and not resolved.is_dir():
        raise NotADirectoryError("リポジトリはディレクトリである必要があります")
    if not must_exist and not resolved.exists() and not resolved.parent.is_dir():
        raise ValueError("保存先の親フォルダーがありません")
    return resolved


def parse_json(raw: bytes):
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as e:
        raise ValueError(f"出力をUTF-8としてデコードできません: {e}") from e
    if not text.strip():
        return []
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    lines = [line for line in text.splitlines() if line.strip()]
    if not lines:
        return []
    results = []
    for i, line in enumerate(lines):
        try:
            results.append(json.loads(line))
        except json.JSONDecodeError as e:
            raise ValueError(f"行{i+1}のJSONが不正です: {e}") from e
    return results


def run_native(exe, repo, password, args, cancel, timeout=3600, max_output=32 * 1024 * 1024, from_password=""):
    if not isinstance(password, str) or not password:
        raise ValueError("パスワードは文字列である必要があります")
    if len(password) > 1024 or "\x00" in password or "\r" in password or "\n" in password:
        raise ValueError("パスワードに無効な長さまたは制御文字が含まれています")
    if not isinstance(from_password, str):
        raise ValueError("from_passwordは文字列である必要があります")
    if len(from_password) > 1024 or "\x00" in from_password or "\r" in from_password or "\n" in from_password:
        raise ValueError("from_passwordに無効な長さまたは制御文字が含まれています")
    if not isinstance(args, list) or not args:
        raise ValueError("引数はリストである必要があります")
    for a in args:
        if not isinstance(a, str) or "\x00" in a:
            raise ValueError("すべての引数はNULを含まない文字列である必要があります")
    if len(args) > 256:
        raise ValueError("引数は最大256個です")
    total_len = sum(len(a) for a in args)
    if total_len > 24000:
        raise ValueError("引数の合計長が24000文字を超えています")
    if not isinstance(timeout, (int, float)) or timeout <= 0 or timeout > 3600:
        raise ValueError("timeoutは0より大きく3600以下の数値である必要があります")
    if not isinstance(max_output, int) or max_output <= 0 or max_output > 64 * 1024 * 1024:
        raise ValueError("max_outputは0より大きく64MiB以下の整数である必要があります")

    repo_path = local_repository(repo, must_exist=(args[0] != "init"))
    cmd = [str(exe), "--repo", str(repo_path), "--json", "--no-cache"] + args

    env = os.environ.copy()
    for k in list(env.keys()):
        if k.upper().startswith("RESTIC_"):
            del env[k]
    env["RESTIC_PASSWORD"] = password
    if from_password:
        env["RESTIC_FROM_PASSWORD"] = from_password

    stderr_cap = 4 * 1024 * 1024
    stdout_bytes = b""
    stderr_text = ""
    rc = None
    partial = False

    with tempfile.TemporaryDirectory(prefix="restic_job_") as job_dir:
        if cancel.is_set():
            raise InterruptedError("キャンセルされました")
        proc = None
        try:
            with open(os.path.join(job_dir, "stdout.bin"), "wb") as sf, \
                 open(os.path.join(job_dir, "stderr.txt"), "w", encoding="utf-8") as ef:
                proc = subprocess.Popen(
                    cmd, stdin=subprocess.DEVNULL, stdout=sf, stderr=ef,
                    env=env, cwd=job_dir, creationflags=subprocess.CREATE_NO_WINDOW, shell=False
                )
            start = time.monotonic()
            while proc.poll() is None:
                if cancel.is_set():
                    raise InterruptedError("キャンセルされました")
                if time.monotonic() - start > timeout:
                    raise TimeoutError("タイムアウトしました")
                if os.path.getsize(os.path.join(job_dir,"stdout.bin")) > max_output or os.path.getsize(os.path.join(job_dir,"stderr.txt")) > stderr_cap:
                    raise ValueError("出力が上限を超えました")
                time.sleep(0.05)

            with open(os.path.join(job_dir, "stdout.bin"), "rb") as f:
                stdout_bytes = f.read(max_output + 1)
            if len(stdout_bytes) > max_output:
                raise ValueError("標準出力が上限を超えました")
            if os.path.getsize(os.path.join(job_dir,"stderr.txt")) > stderr_cap:
                raise ValueError("標準エラー出力が上限を超えました")
            with open(os.path.join(job_dir, "stderr.txt"), "r", encoding="utf-8", errors="replace") as f:
                stderr_text = f.read(stderr_cap + 1)
            if len(stderr_text) > stderr_cap:
                raise ValueError("標準エラー出力が上限を超えました")

            if cancel.is_set():
                raise InterruptedError("停止しました")
            rc = proc.wait()
        except BaseException:
            if proc is not None:
                if proc.poll() is None: proc.kill()
                proc.wait()
            if cancel.is_set():
                raise InterruptedError("キャンセルされました")
            raise

    if password and password in stderr_text:
        stderr_text = stderr_text.replace(password, "***")
    if from_password and from_password in stderr_text:
        stderr_text = stderr_text.replace(from_password, "***")

    if rc == 0:
        return {"stdout": stdout_bytes, "stderr": stderr_text, "returncode": rc, "partial": False}
    if rc == 3 and args[0] == "backup":
        return {"stdout": stdout_bytes, "stderr": stderr_text, "returncode": rc, "partial": True}

    msgs = {10: "リポジトリの初期化が必要です", 11: "保管庫は使用中です", 12: "パスワードが一致しません"}
    msg = msgs.get(rc, f"ネイティブコマンドがエラー終了しました (コード {rc})")
    raise RuntimeError(f"{msg}\n{stderr_text[-2000:]}")
