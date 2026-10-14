import re
DRIVE=re.compile(r"^[A-Za-z]:\\$")

def clean(value: object, limit: int = 120) -> str:
    if not isinstance(value, str):
        return ""
    return "".join(character for character in value if character.isprintable())[:limit].strip()


def size(value: object) -> str:
    if not isinstance(value, (int, float)) or isinstance(value, bool) or value < 0:
        return ""
    gib = value / (1024 ** 3)
    return f"{gib:.1f} GiB"


def summarize(data: object) -> list[tuple[str, str]]:
    """Extract only allowlisted fields from fastfetch's JSON output."""
    if not isinstance(data, list):
        raise ValueError("システム情報の形式が予期しないものです。")
    modules = {entry["type"]: entry.get("result") for entry in data
               if isinstance(entry, dict) and isinstance(entry.get("type"), str)}
    rows: list[tuple[str, str]] = []
    os_data = modules.get("OS")
    if isinstance(os_data, dict):
        os_name = clean(os_data.get("prettyName"))
        if os_name:
            rows.append(("OS", os_name))
    cpu = modules.get("CPU")
    if isinstance(cpu, dict):
        cpu_name = clean(cpu.get("cpu"))
        if cpu_name:
            rows.append(("CPU", cpu_name))
        cores = cpu.get("cores")
        if isinstance(cores, dict):
            physical, logical = cores.get("physical"), cores.get("logical")
            if isinstance(physical, int) and isinstance(logical, int) and 0 < physical <= logical <= 1024:
                rows.append(("CPUコア", f"{physical}コア / {logical}スレッド"))
    gpus = modules.get("GPU")
    if isinstance(gpus, list):
        for index, gpu in enumerate(gpus[:4], 1):
            if isinstance(gpu, dict):
                name = clean(gpu.get("name"))
                if name:
                    rows.append((f"GPU {index}", name))
    memory = modules.get("Memory")
    if isinstance(memory, dict):
        total, used = size(memory.get("total")), size(memory.get("used"))
        if total:
            rows.append(("メモリ", f"{total}（使用中 {used}）" if used else total))
    disks = modules.get("Disk")
    if isinstance(disks, list):
        for disk in disks[:12]:
            if not isinstance(disk, dict):
                continue
            mount = disk.get("mountpoint")
            values = disk.get("bytes")
            if not isinstance(mount, str) or not DRIVE.fullmatch(mount) or not isinstance(values, dict):
                continue
            total, free = size(values.get("total")), size(values.get("available"))
            if total:
                rows.append((f"ドライブ {mount[:2].upper()}", f"合計 {total} / 空き {free}" if free else f"合計 {total}"))
    displays = modules.get("Display")
    if isinstance(displays, list):
        for index, display in enumerate(displays[:6], 1):
            if not isinstance(display, dict) or not isinstance(display.get("output"), dict):
                continue
            output = display["output"]
            width, height = output.get("width"), output.get("height")
            if not (isinstance(width, int) and isinstance(height, int) and 1 <= width <= 20000 and 1 <= height <= 20000):
                continue
            hz = output.get("refreshRate")
            rate = f" / {hz:.0f} Hz" if isinstance(hz, (int, float)) and 1 <= hz <= 1000 else ""
            rows.append((f"画面 {index}", f"{width} × {height}{rate}"))
    if not rows:
        raise ValueError("表示できるシステム情報がありません。")
    return rows
