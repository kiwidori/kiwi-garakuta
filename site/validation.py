from __future__ import annotations
import re
from pathlib import Path
from urllib.parse import urlparse
ROOT = Path(__file__).resolve().parents[1]
SLUG = re.compile(r"^[a-z0-9][a-z0-9-]{1,62}$")

def require_tool(item: dict) -> None:
    needed = ("slug", "name", "summary", "features", "steps", "limitations",
              "screenshot", "download_url", "source_url", "upstream_url", "upstream_license")
    if not all(item.get(key) for key in needed):
        raise ValueError(f"Tool entry missing content: {item.get('slug', '<unknown>')}")
    if not SLUG.fullmatch(item["slug"]):
        raise ValueError(f"Invalid tool slug: {item['slug']}")
    if not item["download_url"].startswith("https://github.com/"):
        raise ValueError(f"Download must be a GitHub URL: {item['slug']}")
    if not item["source_url"].startswith("https://github.com/"):
        raise ValueError(f"Source must be a GitHub URL: {item['slug']}")
    if not item["upstream_url"].startswith("https://github.com/"):
        raise ValueError(f"Upstream must be a GitHub URL: {item['slug']}")
    if item.get("dependency_source_url"):
        parsed = urlparse(item["dependency_source_url"])
        if (parsed.scheme != "https" or parsed.netloc != "github.com" or
                not parsed.path.startswith("/kiwidori/kiwi-garakuta/releases/download/") or
                not parsed.path.endswith(".zip") or parsed.query or parsed.fragment):
            raise ValueError(f"Invalid dependency source download: {item['slug']}")
    if not item["screenshot"].startswith("/assets/screenshots/"):
        raise ValueError(f"Screenshot must be local: {item['slug']}")
    if not (ROOT / "site" / item["screenshot"].lstrip("/")).is_file():
        raise ValueError(f"Screenshot not found: {item['screenshot']}")
    for shot in item.get("workflow_screenshots", []):
        if (not isinstance(shot, dict) or not isinstance(shot.get("src"), str) or
                not shot["src"].startswith("/assets/screenshots/") or ".." in shot["src"] or
                not isinstance(shot.get("caption"), str) or not shot["caption"].strip() or
                not (ROOT / "site" / shot["src"].lstrip("/")).is_file()):
            raise ValueError(f"Workflow screenshot not found: {item['slug']}")
    advanced_shot = item.get("advanced_screenshot")
    if advanced_shot and (not advanced_shot.startswith("/assets/screenshots/") or
                          not (ROOT / "site" / advanced_shot.lstrip("/")).is_file()):
        raise ValueError(f"Advanced screenshot not found: {item['slug']}")
    if not isinstance(item["features"], list) or not isinstance(item["steps"], list):
        raise ValueError(f"Features and steps must be lists: {item['slug']}")
    if not item.get("windows_test_passed"):
        raise ValueError(f"Windows test not passed: {item['slug']}")
    for upstream in item.get("upstreams", []):
        if not upstream.get("name") or not upstream.get("license") or not upstream.get("url", "").startswith("https://github.com/"):
            raise ValueError(f"Invalid upstream project: {item['slug']}")
    for model in item.get("model_sources", []):
        parsed = urlparse(model.get("url", ""))
        if (not model.get("name") or not model.get("license") or parsed.scheme != "https" or
                parsed.netloc not in ("huggingface.co", "github.com") or not parsed.path.strip("/")):
            raise ValueError(f"Invalid model source: {item['slug']}")
    for link in item.get("amazon_links", []):
        parsed = urlparse(link.get("url", ""))
        if not link.get("label") or parsed.scheme != "https" or parsed.hostname not in ("www.amazon.co.jp", "amazon.co.jp", "amzn.to"):
            raise ValueError(f"Invalid Amazon link: {item['slug']}")
