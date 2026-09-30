#!/usr/bin/env python3
"""Build the static catalog from validated, released tool metadata."""

from __future__ import annotations

import html
import json
import re
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "dist"
SLUG = re.compile(r"^[a-z0-9][a-z0-9-]{1,62}$")


def esc(value: object) -> str:
    return html.escape(str(value), quote=True)


def page(title: str, description: str, body: str, site_name: str, contact: str) -> str:
    return f"""<!doctype html>
<html lang="ja"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="description" content="{esc(description)}"><title>{esc(title)} | {esc(site_name)}</title>
<link rel="stylesheet" href="/assets/style.css"></head><body>
<header><div class="wrap top"><a class="brand" href="/">{esc(site_name)}</a><a class="contact" href="{esc(contact)}" rel="noopener noreferrer">問い合わせ ↗</a></div></header>
<main class="wrap">{body}</main>
<footer><div class="wrap"><p>Windows向けの小さな道具を無料公開しています。各ソフトのライセンスと出典は個別ページに記載しています。</p>
<p><a href="{esc(contact)}" rel="noopener noreferrer">XのDMで問い合わせる ↗</a></p></div></footer>
</body></html>"""


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
    if not item["screenshot"].startswith("/assets/screenshots/"):
        raise ValueError(f"Screenshot must be local: {item['slug']}")
    if not (ROOT / "site" / item["screenshot"].lstrip("/")).is_file():
        raise ValueError(f"Screenshot not found: {item['screenshot']}")
    if not isinstance(item["features"], list) or not isinstance(item["steps"], list):
        raise ValueError(f"Features and steps must be lists: {item['slug']}")
    if not item.get("windows_test_passed"):
        raise ValueError(f"Windows test not passed: {item['slug']}")


def tool_page(item: dict, site_name: str, contact: str) -> str:
    features = "".join(f"<li>{esc(value)}</li>" for value in item["features"])
    steps = "".join(f"<li>{esc(value)}</li>" for value in item["steps"])
    body = f"""<nav class="crumb"><a href="/">一覧</a> / {esc(item['name'])}</nav>
<section class="hero"><div class="eyebrow">Windows 11 · 無料 · ZIP版</div><h1>{esc(item['name'])}</h1>
<p class="lead">{esc(item['summary'])}</p>
<div class="actions"><a class="button" href="{esc(item['download_url'])}" rel="noopener noreferrer">ZIPをダウンロード ↗</a>
<a class="textlink" href="{esc(item['source_url'])}" rel="noopener noreferrer">ソースコード ↗</a></div></section>
<figure class="shot"><img src="{esc(item['screenshot'])}" alt="{esc(item['name'])}の実際の画面" loading="lazy">
<figcaption>実際の動作画面</figcaption></figure>
<section><h2>できること</h2><ul>{features}</ul></section>
<section><h2>使い方</h2><ol>{steps}</ol></section>
<section><h2>制限と注意点</h2><p>{esc(item['limitations'])}</p></section>
<section class="origin"><h2>元になったソフト</h2><p><a href="{esc(item['upstream_url'])}" rel="noopener noreferrer">上流プロジェクト ↗</a>
（ライセンス: {esc(item['upstream_license'])}）</p><p>本ソフトは上流プロジェクトの公式製品ではありません。</p></section>
<section class="support"><h2>開発を支援する</h2><p>ソフトは無料で使えます。開発支援リンクは準備中です。</p>
<p class="muted">関連商品の紹介は、各サービスの設定が完了した後に掲載します。</p></section>"""
    return page(item["name"], item["summary"], body, site_name, contact)


def main() -> None:
    settings = json.loads((ROOT / "factory.json").read_text(encoding="utf-8"))
    catalog = json.loads((ROOT / "catalog.json").read_text(encoding="utf-8"))
    if not isinstance(catalog, list):
        raise ValueError("catalog.json must be a list")
    seen = set()
    for item in catalog:
        require_tool(item)
        if item["slug"] in seen:
            raise ValueError(f"Duplicate slug: {item['slug']}")
        seen.add(item["slug"])
    if DIST.resolve().parent != ROOT.resolve() or DIST.is_symlink():
        raise ValueError("Output directory must be a normal directory inside the project")
    if DIST.exists():
        shutil.rmtree(DIST)
    shutil.copytree(ROOT / "site" / "assets", DIST / "assets")
    cards = "".join(
        f'<a class="card" href="/tools/{esc(item["slug"])}/"><span class="tag">Windows 11</span>'
        f'<h2>{esc(item["name"])}</h2><p>{esc(item["summary"])}</p><span class="cardmore">詳しく見る →</span></a>'
        for item in catalog
    )
    if not cards:
        cards = '<p class="empty">公開準備中です。動作確認を終えたソフトから掲載します。</p>'
    homepage = f"""<section class="homehero"><div class="eyebrow">無料のWindowsツール</div>
<h1>ちょっと便利な、<br>きういのガラクタ。</h1>
<p class="lead">CUIツールを使いやすくした小さなソフトを公開しています。ダウンロードは無料です。</p></section>
<section class="listing"><h2>公開中のソフト</h2><div class="grid">{cards}</div></section>"""
    (DIST / "index.html").write_text(page(settings["site_name"], "無料のWindows向けツールを公開しています。", homepage,
                                           settings["site_name"], settings["contact_url"]), encoding="utf-8")
    for item in catalog:
        directory = DIST / "tools" / item["slug"]
        directory.mkdir(parents=True, exist_ok=True)
        (directory / "index.html").write_text(tool_page(item, settings["site_name"], settings["contact_url"]), encoding="utf-8")
    print(f"Built {len(catalog)} tool pages in {DIST}")


if __name__ == "__main__":
    main()
