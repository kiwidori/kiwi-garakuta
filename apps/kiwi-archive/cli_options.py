import ntpath

FORMAT_CHOICES = (
    "zip", "7z", "tar", "tar.gz", "tar.xz", "tar.zst", "tar.bz2", "tar.lz4",
    "tar.sz", "tar.br", "tar.bz3", "tar.lzma", "tar.lz",
    "gz", "xz", "zst", "bz2", "bz3", "lz4", "sz", "br", "lzma", "lz"
)

_ALIASES = {
    "tgz": "tar.gz", "tbz": "tar.bz2", "tbz2": "tar.bz2", "txz": "tar.xz",
    "tlz4": "tar.lz4", "tsz": "tar.sz", "tzst": "tar.zst", "tlzma": "tar.lzma",
    "tlz": "tar.lz", "cbz": "zip", "cb7": "7z", "cbt": "tar", "cbr": "rar"
}

_BASES = {"zip", "7z", "tar", "gz", "xz", "zst", "bz2", "bz3", "lz4", "sz", "br", "lzma", "lz"}


import ntpath

def normalize_format(text, compress=False):
    if not isinstance(text, str) or not text:
        raise ValueError("形式が空です")
    t = text.strip().lower()
    if any(c.isspace() for c in t) or any(c in t for c in "/\\:*?\"<>|"):
        raise ValueError("無効な形式文字列です")

    if t in _ALIASES:
        t = _ALIASES[t]

    bases = _BASES | {"rar", "bz", "lzip"}
    parts = t.split(".")
    if len(parts) > 4:
        raise ValueError("形式の連鎖が長すぎます")

    for i, p in enumerate(parts):
        if p == "bz":
            parts[i] = "bz2"
        elif p == "lzip":
            parts[i] = "lz"

    if not all(p in bases for p in parts):
        raise ValueError("未知の形式です")

    archives = [p for p in parts if p in ("tar", "zip", "7z", "rar")]
    if len(archives) > 1:
        raise ValueError("ネストしたアーカイブは禁止です")
    if archives and archives[0] != parts[0]:
        raise ValueError("アーカイブ形式は先頭でなければなりません")

    if "tar" in parts and parts[0] != "tar":
        raise ValueError("tarは先頭でなければなりません")

    if "rar" in parts:
        if compress:
            raise ValueError("RAR圧縮は禁止されています")

    return ".".join(parts)


def build_args(op, paths, output=None, options=None):
    if op not in ("compress", "decompress", "list"):
        raise ValueError("無効な操作です")

    opts = options or {}

    threads = opts.get("threads", 1)
    if isinstance(threads, bool) or not isinstance(threads, int) or not (1 <= threads <= 16):
        raise ValueError("スレッド数は1〜16の整数で指定してください")

    args = ["--accessible", "--yes", "--threads", str(threads), op]

    if opts.get("hidden"):
        args.append("--hidden")
    if opts.get("gitignore"):
        args.append("--gitignore")

    fmt = opts.get("format")
    if fmt:
        norm_fmt = normalize_format(fmt, compress=(op == "compress"))
        args.extend(["--format", norm_fmt])

    if op == "compress":
        mode = opts.get("mode", "auto")
        level = opts.get("level")

        if mode not in ("auto", "fast", "slow", "level"):
            raise ValueError("無効なモードです")

        if mode == "fast":
            args.append("--fast")
        elif mode == "slow":
            args.append("--slow")
        elif mode == "level":
            if isinstance(level, bool) or not isinstance(level, int) or not (-7 <= level <= 22):
                raise ValueError("レベルは-7〜22の整数で指定してください")
            args.append(f"--level={level}")

        if not output:
            raise ValueError("圧縮時は出力パスが必須です")
        if "\x00" in output or not ntpath.isabs(output):
            raise ValueError("出力パスはNULを含まない絶対パスでなければなりません")

    elif op == "decompress":
        if not output:
            raise ValueError("解凍時は出力ディレクトリが必須です")
        if "\x00" in output or not ntpath.isabs(output):
            raise ValueError("出力ディレクトリはNULを含まない絶対パスでなければなりません")
        args.extend(["--dir", output])

    elif op == "list":
        if opts.get("tree"):
            args.append("--tree")

    if not paths:
        raise ValueError("入力パスが空です")

    if len(paths) > 32:
        raise ValueError("最大32ルートまでです")

    for p in paths:
        if not isinstance(p, str) or not p:
            raise ValueError("無効なパスです")
        if "\x00" in p or not ntpath.isabs(p):
            raise ValueError("NULを含まない絶対パスでなければなりません")

    args.append("--")
    for p in paths:
        args.append(p)

    if op == "compress":
        args.append(output)

    return args
