"""Refuse site deployment when a listed download or source is missing."""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def available(url: str) -> bool:
    request = urllib.request.Request(url, method="HEAD", headers={
        "User-Agent": "kiwi-garakuta-publish/0.1",
        "Accept": "application/octet-stream",
    })
    retryable_codes = (429, 500, 502, 503, 504)
    for attempt in range(3):
        try:
            with urllib.request.urlopen(request, timeout=20) as response:
                return response.status == 200
        except urllib.error.HTTPError as error:
            if error.code not in retryable_codes:
                return False
        except (urllib.error.URLError, TimeoutError):
            pass
        if attempt < 2:
            time.sleep(1 + attempt)
    return False


def main() -> None:
    catalog = json.loads((ROOT / "catalog.json").read_text(encoding="utf-8"))
    for item in catalog:
        for field in ("download_url", "source_url", "upstream_url"):
            url = item[field]
            if not available(url):
                raise SystemExit(f"Cannot publish {item['slug']}: {field} is unavailable: {url}")
            print(f"OK: {item['slug']} {field}")


if __name__ == "__main__":
    main()
