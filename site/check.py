#!/usr/bin/env python3
"""Check the generated catalog, navigation, assets, and page metadata."""

from __future__ import annotations

import argparse
import json
import re
import sys
import xml.etree.ElementTree as ET
from collections import Counter
from dataclasses import dataclass, field
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urljoin, urlsplit

ROOT = Path(__file__).resolve().parents[1]
VOID = frozenset("area base br col embed hr img input link meta param source track wbr".split())
NON_TEXT = frozenset(("script", "style", "template"))
PRIVATE_PARTS = frozenset(("data", "factory", ".git", ".tools"))
PRIVATE_FILES = frozenset(("agents.md", "factory.json", ".env"))


def normal(value: str) -> str:
    return " ".join(value.split())


@dataclass
class Element:
    tag: str
    attrs: dict[str, str]
    line: int
    parent: Element | None = None
    children: list[Element | str] = field(default_factory=list)

    def text(self) -> str:
        if self.tag in NON_TEXT:
            return ""
        return " ".join(child.text() if isinstance(child, Element) else child
                        for child in self.children)

    def ancestors(self):
        node = self.parent
        while node is not None:
            yield node
            node = node.parent

    def concealed(self) -> bool:
        return any("hidden" in node.attrs or "inert" in node.attrs
                   for node in (self, *self.ancestors()))


class Document(HTMLParser):
    def __init__(self, path: Path, route: str):
        super().__init__(convert_charrefs=True)
        self.path, self.route = path, route
        self.root = Element("document", {}, 1)
        self.stack = [self.root]
        self.elements: list[Element] = []
        self.parse_errors: list[str] = []
        self.doctype = False

    def handle_decl(self, decl: str):
        self.doctype |= decl.lower() == "doctype html"

    def handle_starttag(self, tag: str, attrs):
        names = [name for name, _ in attrs]
        duplicate = [name for name, count in Counter(names).items() if count > 1]
        if duplicate:
            self.parse_errors.append(f"line {self.getpos()[0]}: duplicate attributes {duplicate}")
        node = Element(tag, {key: value or "" for key, value in attrs},
                       self.getpos()[0], self.stack[-1])
        self.stack[-1].children.append(node)
        self.elements.append(node)
        if tag not in VOID:
            self.stack.append(node)

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in VOID:
            self.handle_endtag(tag)

    def handle_endtag(self, tag: str):
        if tag in VOID:
            return
        if len(self.stack) == 1 or self.stack[-1].tag != tag:
            self.parse_errors.append(f"line {self.getpos()[0]}: unmatched closing </{tag}>")
            for index in range(len(self.stack) - 1, 0, -1):
                if self.stack[index].tag == tag:
                    del self.stack[index:]
                    return
        else:
            self.stack.pop()

    def handle_data(self, value: str):
        self.stack[-1].children.append(value)

    def finish(self):
        self.close()
        if len(self.stack) != 1:
            self.parse_errors.append("unclosed elements: " + ", ".join(n.tag for n in self.stack[1:]))

    def select(self, tag: str) -> list[Element]:
        return [node for node in self.elements if node.tag == tag]


class SiteCheck:
    def __init__(self, dist: Path, catalog: list[dict], base_url: str):
        self.dist = dist.resolve()
        self.catalog = catalog
        self.base_url = base_url.rstrip("/") + "/"
        self.origin = urlsplit(self.base_url)
        self.documents: dict[str, Document] = {}
        self.errors: list[str] = []
        self.local_links = 0
        self.images = 0

    def error(self, route: str, message: str):
        self.errors.append(f"{route}: {message}")

    def public_route(self, path: Path) -> str:
        relative = path.relative_to(self.dist).as_posix()
        return "/" + relative.removesuffix("index.html") if path.name == "index.html" else "/" + relative

    def load(self):
        if not self.dist.is_dir():
            raise ValueError(f"Output directory not found: {self.dist}")
        for path in sorted(self.dist.rglob("*")):
            if path.is_symlink():
                self.error("/", f"output contains a symbolic link: {path.relative_to(self.dist)}")
                continue
            if not path.is_file():
                continue
            relative = path.relative_to(self.dist)
            if any(part.lower() in PRIVATE_PARTS for part in relative.parts) or path.name.lower() in PRIVATE_FILES:
                self.error("/", f"private file in output: {relative.as_posix()}")
            if path.suffix.lower() != ".html":
                continue
            route = self.public_route(path)
            doc = Document(path, route)
            doc.feed(path.read_text(encoding="utf-8"))
            doc.finish()
            self.documents[route] = doc
            for message in doc.parse_errors:
                self.error(route, message)

    def resolve(self, source_route: str, value: str) -> tuple[str, Path, str] | None:
        url = urlsplit(urljoin(self.base_url, source_route))
        target = urlsplit(urljoin(url.geturl(), value))
        if target.scheme not in ("http", "https"):
            return None
        if target.netloc.lower() != self.origin.netloc.lower():
            return None
        decoded = unquote(target.path)
        if "\\" in decoded or "\x00" in decoded:
            self.error(source_route, f"invalid local URL: {value}")
            return None
        parts = Path(decoded.lstrip("/")).parts
        if any(part.lower() in PRIVATE_PARTS for part in parts) or (parts and parts[-1].lower() in PRIVATE_FILES):
            self.error(source_route, f"link exposes a private path: {value}")
        path = (self.dist / decoded.lstrip("/")).resolve()
        if not path.is_relative_to(self.dist):
            self.error(source_route, f"local URL escapes the output directory: {value}")
            return None
        if decoded.endswith("/") or path.is_dir():
            path /= "index.html"
        return decoded, path, unquote(target.fragment)

    def link(self, doc: Document, value: str, kind: str = "link"):
        if not value.strip():
            self.error(doc.route, f"empty {kind}")
            return
        scheme = urlsplit(value).scheme.lower()
        if scheme in ("javascript", "vbscript") or (scheme == "data" and kind != "image"):
            self.error(doc.route, f"unsafe {kind} scheme: {scheme}")
            return
        parsed = urlsplit(value)
        own_repository = "/kiwidori/kiwi-garakuta/"
        if parsed.netloc.lower() == "github.com" and parsed.path.lower().startswith(own_repository):
            parts = unquote(parsed.path).lower().split("/")
            if any(part in PRIVATE_PARTS or part in PRIVATE_FILES for part in parts[3:]):
                self.error(doc.route, f"link exposes a private repository path: {value}")
        result = self.resolve(doc.route, value)
        if result is None:
            return
        _, path, fragment = result
        self.local_links += 1
        if not path.is_file():
            self.error(doc.route, f"missing local {kind}: {value}")
            return
        if fragment and path.suffix.lower() == ".html":
            other = self.documents.get(self.public_route(path))
            ids = {node.attrs.get("id") for node in other.elements} if other else set()
            if fragment not in ids:
                self.error(doc.route, f"missing fragment target: {value}")

    def check_document(self, doc: Document):
        route = doc.route
        ids = [node.attrs["id"] for node in doc.elements if "id" in node.attrs]
        for name, count in Counter(ids).items():
            if not name or count != 1:
                self.error(route, f"empty or duplicate id: {name!r}")
        id_nodes = {node.attrs["id"]: node for node in doc.elements if node.attrs.get("id")}
        if not doc.doctype:
            self.error(route, "HTML5 doctype is missing")
        html_nodes = doc.select("html")
        if len(html_nodes) != 1 or not html_nodes[0].attrs.get("lang", "").startswith("ja"):
            self.error(route, "one Japanese-language html element is required")
        for tag in ("title", "main", "h1"):
            nodes = doc.select(tag)
            if tag == "title":
                nodes = [node for node in nodes if any(parent.tag == "head" for parent in node.ancestors())]
            if len(nodes) != 1 or not normal(nodes[0].text()):
                self.error(route, f"one non-empty {tag} is required")
        if any(node.concealed() for node in doc.select("main")):
            self.error(route, "main content is hidden")
        meta = {}
        for node in doc.select("meta"):
            key = node.attrs.get("name", node.attrs.get("property", "")).lower()
            if key:
                meta.setdefault(key, []).append(node.attrs.get("content", ""))
        for key in ("description", "viewport", "og:title", "og:description", "og:type", "og:url", "og:image"):
            if len(meta.get(key, [])) != 1 or not meta[key][0].strip():
                self.error(route, f"one non-empty {key} metadata value is required")
        expected_url = urljoin(self.base_url, route)
        canonicals = [node.attrs.get("href", "") for node in doc.select("link")
                      if "canonical" in node.attrs.get("rel", "").split()]
        if canonicals != [expected_url]:
            self.error(route, f"canonical must be {expected_url}")
        if meta.get("og:url") != [expected_url]:
            self.error(route, "og:url and canonical disagree")
        for image in meta.get("og:image", []):
            self.link(doc, image, "social image")
        for node in doc.elements:
            attrs = node.attrs
            if "hidden" in attrs and attrs["hidden"] not in ("", "hidden", "until-found"):
                self.error(route, f"line {node.line}: invalid hidden value {attrs['hidden']!r}")
            for reference in ("aria-labelledby", "aria-describedby", "aria-controls"):
                for name in attrs.get(reference, "").split():
                    if name not in id_nodes:
                        self.error(route, f"line {node.line}: {reference} references missing #{name}")
            if attrs.get("aria-hidden") == "true" and not node.concealed():
                if node.tag in ("a", "button", "input", "select", "textarea") and attrs.get("tabindex") != "-1" and "disabled" not in attrs:
                    self.error(route, f"line {node.line}: focusable {node.tag} is aria-hidden")
            if node.tag in ("a", "button") and any(parent.tag in ("a", "button") for parent in node.ancestors()):
                self.error(route, f"line {node.line}: nested interactive controls")
            if node.tag == "button":
                label = normal(node.text()) or normal(attrs.get("aria-label", ""))
                label = label or any(normal(id_nodes[name].text()) for name in attrs.get("aria-labelledby", "").split() if name in id_nodes)
                if not label:
                    self.error(route, f"line {node.line}: button has no accessible label")
            if node.tag in ("a", "link") and "href" in attrs:
                self.link(doc, attrs["href"])
            if node.tag in ("script", "img", "source", "video", "audio", "iframe") and "src" in attrs:
                self.link(doc, attrs["src"], "image" if node.tag == "img" else "asset")
            if node.tag == "img":
                self.images += 1
                if "alt" not in attrs:
                    self.error(route, f"line {node.line}: image is missing alt")
                if not all(re.fullmatch(r"[1-9][0-9]*", attrs.get(key, "")) for key in ("width", "height")):
                    self.error(route, f"line {node.line}: image dimensions are missing or invalid")
            if node.tag == "label" and "for" in attrs:
                target = id_nodes.get(attrs["for"])
                if target is None or target.tag not in ("input", "select", "textarea", "button", "meter", "progress", "output"):
                    self.error(route, f"line {node.line}: label has no matching control")
            if node.tag in ("input", "select", "textarea") and attrs.get("type", "").lower() not in ("hidden", "button", "submit", "reset", "image"):
                labels = [label for label in doc.select("label") if label.attrs.get("for") == attrs.get("id") and attrs.get("id")]
                labels += [parent for parent in node.ancestors() if parent.tag == "label"]
                labelled = bool(normal(attrs.get("aria-label", ""))) or any(normal(label.text()) for label in labels)
                labelled |= any(normal(id_nodes[name].text()) for name in attrs.get("aria-labelledby", "").split() if name in id_nodes)
                if not labelled:
                    self.error(route, f"line {node.line}: {node.tag} has no accessible label")
        if not any(node.tag == "a" and node.attrs.get("href") == "#" + main.attrs.get("id", "")
                   for main in doc.select("main") if main.attrs.get("id") for node in doc.elements):
            self.error(route, "skip link to main content is missing")

    def check_catalog(self):
        home = self.documents.get("/")
        if home is None:
            self.error("/", "home page is missing")
            return
        home_links = {node.attrs.get("href") for node in home.select("a")}
        if "/guide/" not in home_links:
            self.error("/", "getting-started guide is not linked")
        if not any(node.attrs.get("src") for node in home.select("script")):
            self.error("/", "catalog interaction script is missing")
        for item in self.catalog:
            route = f'/tools/{item["slug"]}/'
            doc = self.documents.get(route)
            if doc is None:
                self.error(route, "catalog page is missing")
                continue
            text = normal(doc.root.text())
            for key in ("name", "summary", "limitations"):
                expected = normal(item[key])
                actual = text
                if key == "limitations":
                    expected = "".join(expected.split())
                    actual = "".join(actual.split())
                if expected not in actual:
                    self.error(route, f"catalog {key} text is missing or changed")
            for key in ("features", "steps"):
                for value in item[key]:
                    if normal(value) not in text:
                        self.error(route, f"catalog {key} entry is missing: {value[:55]}")
            links = [node.attrs.get("href") for node in doc.select("a")]
            for key in ("download_url", "source_url"):
                if item[key] not in links:
                    self.error(route, f"catalog {key} link is missing")
            images = {node.attrs.get("src") for node in doc.select("img")}
            expected_images = [item["screenshot"]] + [shot["src"] for shot in item.get("workflow_screenshots", [])]
            if item.get("advanced_screenshot"):
                expected_images.append(item["advanced_screenshot"])
            for image in expected_images:
                if image not in images:
                    self.error(route, f"catalog screenshot is missing: {image}")
            if item.get("replaced_by"):
                target = f'/tools/{item["replaced_by"]}/'
                if target not in links:
                    self.error(route, "replacement tool is not linked")
                elif item["download_url"] in links and links.index(target) > links.index(item["download_url"]):
                    self.error(route, "replacement link comes after the old download")
            elif route not in home_links:
                self.error("/", f"current tool is not linked: {route}")

    def check_discovery(self, path: Path):
        if not path.is_file():
            return
        discovery = json.loads(path.read_text(encoding="utf-8"))
        home = self.documents.get("/")
        home_links = {urlsplit(node.attrs.get("href", "")).path for node in home.select("a")} if home else set()
        for category in discovery.get("categories", []):
            route = f'/categories/{category["id"]}/'
            doc = self.documents.get(route)
            if doc is None:
                self.error(route, "category page is missing")
                continue
            if route not in home_links:
                self.error("/", f"category is not linked: {route}")
            links = {node.attrs.get("href") for node in doc.select("a")}
            for item in self.catalog:
                data = discovery.get("tools", {}).get(item["slug"], {})
                if not item.get("replaced_by") and data.get("category") == category["id"]:
                    target = f'/tools/{item["slug"]}/'
                    if target not in links:
                        self.error(route, f"category tool is not linked: {target}")

    def check_sitemap(self):
        sitemap = self.dist / "sitemap.xml"
        if not sitemap.is_file():
            self.error("/sitemap.xml", "sitemap is missing")
            return
        try:
            tree = ET.fromstring(sitemap.read_text(encoding="utf-8"))
        except ET.ParseError as exc:
            self.error("/sitemap.xml", f"invalid XML: {exc}")
            return
        locations = [normal(node.text or "") for node in tree.iter() if node.tag.split("}")[-1] == "loc"]
        if len(set(locations)) != len(locations):
            self.error("/sitemap.xml", "duplicate locations")
        expected = {urljoin(self.base_url, route) for route in self.documents if route != "/404.html"}
        actual = set(locations)
        for value in sorted(expected - actual):
            self.error("/sitemap.xml", f"page is absent: {value}")
        for value in sorted(actual - expected):
            self.error("/sitemap.xml", f"unexpected or missing page: {value}")
        robots = self.dist / "robots.txt"
        if not robots.is_file():
            self.error("/robots.txt", "robots.txt is missing")
            return
        contents = robots.read_text(encoding="utf-8")
        if not re.search(r"(?im)^sitemap:\s*" + re.escape(urljoin(self.base_url, "sitemap.xml")) + r"\s*$", contents):
            self.error("/robots.txt", "sitemap URL is missing")
        if re.search(r"(?im)^disallow:\s*/\s*$", contents):
            self.error("/robots.txt", "all pages are blocked from indexing")

    def check_stylesheets(self):
        for path in sorted(self.dist.rglob("*.css")):
            route = "/" + path.relative_to(self.dist).as_posix()
            doc = Document(path, route)
            text = re.sub(r"/\*.*?\*/", "", path.read_text(encoding="utf-8"), flags=re.S)
            for match in re.finditer(r"url\(\s*(['\"]?)(.*?)\1\s*\)", text, flags=re.I):
                value = match.group(2).strip()
                if value and not value.startswith("data:"):
                    self.link(doc, value, "stylesheet asset")

    def run(self, discovery: Path):
        self.load()
        for doc in self.documents.values():
            self.check_document(doc)
        self.check_catalog()
        self.check_discovery(discovery)
        self.check_sitemap()
        self.check_stylesheets()
        if "/guide/" not in self.documents:
            self.error("/guide/", "getting-started guide is missing")
        if "/404.html" not in self.documents:
            self.error("/404.html", "not-found page is missing")
        return {
            "ok": not self.errors,
            "pages": len(self.documents),
            "catalog_pages": len(self.catalog),
            "current_tools": sum(not item.get("replaced_by") for item in self.catalog),
            "local_links_checked": self.local_links,
            "images_checked": self.images,
            "errors": self.errors,
        }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dist", type=Path, default=ROOT / "dist")
    parser.add_argument("--catalog", type=Path, default=ROOT / "catalog.json")
    parser.add_argument("--discovery", type=Path, default=ROOT / "site" / "discovery.json")
    parser.add_argument("--base-url", default="https://kiwi-garakuta.pages.dev/")
    parser.add_argument("--json", action="store_true", help="print a JSON report")
    args = parser.parse_args()
    try:
        catalog = json.loads(args.catalog.read_text(encoding="utf-8"))
        if not isinstance(catalog, list):
            raise ValueError("Catalog must be a list")
        base = urlsplit(args.base_url)
        if base.scheme != "https" or not base.netloc or base.path not in ("", "/") or base.query or base.fragment:
            raise ValueError("Base URL must be an HTTPS site origin")
        report = SiteCheck(args.dist, catalog, args.base_url).run(args.discovery)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(f"Site check could not run: {exc}", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        for message in report["errors"]:
            print(f"ERROR {message}")
        print(f'{"Passed" if report["ok"] else "Failed"}: {report["pages"]} pages, '
              f'{report["catalog_pages"]} catalog entries, {report["local_links_checked"]} local links, '
              f'{report["images_checked"]} images, {len(report["errors"])} errors.')
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
