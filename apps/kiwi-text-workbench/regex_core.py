import time,shutil,subprocess,tempfile,threading
from pathlib import Path
from typing import List
MAX_INPUT_BYTES=16*1024
MAX_EXAMPLES=100
MAX_EXAMPLE_CHARS=256
MAX_OUTPUT_BYTES=64*1024
GREX_TIMEOUT_SECONDS=15


def validated_examples(text: str) -> List[str]:
    if not isinstance(text, str):
        raise ValueError("文字列を入力してください。")
    if len(text.encode('utf-8')) > MAX_INPUT_BYTES:
        raise ValueError("入力はUTF-8で16 KiBまでです。")
    if "\x00" in text:
        raise ValueError("NUL文字は入力できません。")
    normalized = text.replace("\r\n", "\n")
    if "\r" in normalized:
        raise ValueError("単独のCR文字は入力できません。")
    if not normalized:
        raise ValueError("例を1行ずつ入力してください。")
    raw_lines = normalized.split("\n")
    examples: List[str] = []
    for line in raw_lines:
        if line == "":
            continue
        if len(line) > MAX_EXAMPLE_CHARS:
            raise ValueError("1行256文字までにしてください。")
        examples.append(line)
    if not examples:
        raise ValueError("例を1行ずつ入力してください。")
    if len(examples) > MAX_EXAMPLES:
        raise ValueError("例は100行までにしてください。")
    encoded = "\n".join(examples).encode("utf-8")
    if len(encoded) > MAX_INPUT_BYTES:
        raise ValueError("入力はUTF-8で16 KiBまでです。")
    return examples

def _sanitize_error(exc: Exception) -> str:
    if isinstance(exc, InterruptedError):
        return "生成を停止しました。"
    if isinstance(exc, TimeoutError):
        return "15秒を超えたため停止しました。例を減らしてください。"
    if isinstance(exc, ValueError) and not isinstance(exc, UnicodeError):
        return str(exc)
    if isinstance(exc, FileNotFoundError):
        return "同梱のgrex.exeが見つかりません。"
    return "生成に失敗しました。"

def _run_grex(
    exe: Path,
    examples: List[str],
    digits: bool,
    ignore_case: bool,
    repetitions: bool,
    cancel: threading.Event,
) -> str:
    if cancel.is_set():
        raise InterruptedError()
    if not exe.is_file():
        raise FileNotFoundError("grex.exe not found")

    tmp_dir = Path(tempfile.mkdtemp(prefix="kiwi-regex-"))
    input_file = tmp_dir / "examples.txt"
    stdout_file = tmp_dir / "stdout.txt"
    stderr_file = tmp_dir / "stderr.txt"

    try:
        input_file.write_text("\n".join(examples), encoding="utf-8")

        cmd = [str(exe.resolve()), "--file", str(input_file)]
        if digits:
            cmd.append("--digits")
        if ignore_case:
            cmd.append("--ignore-case")
        if repetitions:
            cmd.append("--repetitions")

        with open(stdout_file, "wb") as out_fh, open(stderr_file, "wb") as err_fh:
            proc = subprocess.Popen(
                cmd,
                stdout=out_fh,
                stderr=err_fh,
                stdin=subprocess.DEVNULL,
                cwd=str(tmp_dir),
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )

            try:
                deadline = time.monotonic() + GREX_TIMEOUT_SECONDS
                while proc.poll() is None:
                    if cancel.is_set():
                        raise InterruptedError()
                    if time.monotonic() > deadline:
                        raise TimeoutError()
                    if max(stdout_file.stat().st_size, stderr_file.stat().st_size) > MAX_OUTPUT_BYTES:
                        raise ValueError("出力が64 KiBを超えたため停止しました。")
                    time.sleep(0.05)
            finally:
                if proc.poll() is None:
                    proc.kill()
                proc.wait()

            if cancel.is_set():
                raise InterruptedError("cancelled")

            if proc.returncode != 0:
                raise RuntimeError("nonzero exit")

            raw = stdout_file.read_bytes()
            if len(raw) > MAX_OUTPUT_BYTES:
                raise ValueError("出力が64 KiBを超えました。例を減らしてください。")

            text = raw.decode("utf-8")
            text = text.removesuffix("\n").removesuffix("\r")
            if not text:
                raise RuntimeError('empty output')
            return text
    finally:
        if tmp_dir.resolve().parent == Path(tempfile.gettempdir()).resolve() and tmp_dir.name.startswith('kiwi-regex-'):
            shutil.rmtree(tmp_dir, ignore_errors=True)
