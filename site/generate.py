"""Build the static software catalog and browsing pages."""
from __future__ import annotations
import json
import re
import shutil
from pathlib import Path
from urllib.parse import urlparse
from xml.etree import ElementTree as ET
from validation import require_tool, SLUG
from render import BASE, Site

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / 'dist'


def load(name: str):
    return json.loads((ROOT / name).read_text(encoding='utf8'))


def main():
    settings = load('site-settings.json')
    support = load('support.json')
    catalog = load('catalog.json')
    discovery = load('site/discovery.json')
    downloads = load('site/downloads.json')
    for key, hosts in [('contact_url', {'x.com', 'twitter.com'}), ('youtube_url', {'www.youtube.com', 'youtube.com'})]:
        parsed = urlparse(settings[key])
        if parsed.scheme != 'https' or parsed.netloc not in hosts:
            raise ValueError(f'Invalid {key}')
    paypal = support.get('paypal_url', '')
    if paypal and (urlparse(paypal).scheme != 'https' or urlparse(paypal).netloc not in {'paypal.me', 'www.paypal.com', 'paypal.com'}):
        raise ValueError('Invalid PayPal destination')
    qr = support.get('paypal_qr', '')
    if qr and (not paypal or qr != '/assets/paypal-qr.png' or not (ROOT / 'site' / qr.lstrip('/')).is_file()):
        raise ValueError('Invalid PayPal QR asset')
    if not isinstance(catalog, list):
        raise ValueError('Catalog must be a list')
    seen = set()
    for tool in catalog:
        require_tool(tool)
        if tool['slug'] in seen:
            raise ValueError('Duplicate software slug')
        seen.add(tool['slug'])
        download = downloads.get(tool['slug'], {})
        if (download.get('url') != tool['download_url'] or
                type(download.get('bytes')) is not int or download['bytes'] <= 0 or
                (download.get('sha256') is not None and not re.fullmatch(r'[0-9a-f]{64}', download['sha256']))):
            raise ValueError(f'Invalid or outdated download metadata: {tool["slug"]}')
    if set(downloads) != seen:
        raise ValueError('Download metadata must match the catalog')
    active = {item['slug'] for item in catalog if not item.get('replaced_by')}
    for tool in catalog:
        if tool.get('replaced_by') and tool['replaced_by'] not in active:
            raise ValueError('Replacement must point directly to an active tool')
    categories = discovery['categories']
    category_ids = [c['id'] for c in categories]
    if len(set(category_ids)) != len(category_ids) or not all(SLUG.fullmatch(c) for c in category_ids):
        raise ValueError('Invalid category IDs')
    if set(discovery['tools']) != active:
        raise ValueError('Discovery metadata must cover exactly the active software')
    for slug, meta in discovery['tools'].items():
        if meta['category'] not in category_ids or not 1 <= len(meta['tags']) <= 3:
            raise ValueError(f'Invalid category or tags: {slug}')
        if not all(isinstance(v, str) and v.strip() for k in ['tags', 'keywords', 'alias_names'] for v in meta[k]):
            raise ValueError(f'Invalid search metadata: {slug}')
    if len({f['slug'] for f in discovery['featured']}) != len(discovery['featured']):
        raise ValueError('Duplicate featured tools')
    for featured in discovery['featured']:
        if featured['slug'] not in active:
            raise ValueError('Featured tool must be active')
    journey_ids = set()
    for journey in discovery['journeys']:
        if not SLUG.fullmatch(journey['id']) or journey['id'] in journey_ids or not journey['slugs'] or not set(journey['slugs']) <= active:
            raise ValueError('Invalid workflow')
        journey_ids.add(journey['id'])
    if DIST.resolve().parent != ROOT.resolve() or DIST.is_symlink() or getattr(DIST, 'is_junction', lambda: False)():
        raise ValueError('Output must be a normal directory inside this project')
    site = Site(settings, support, catalog, discovery, downloads)
    pages = {'/': site.home(), '/guide/': site.guide(), '/404.html': site.not_found()}
    pages.update({f'/tools/{tool["slug"]}/': site.tool(tool) for tool in catalog})
    pages.update({f'/categories/{category["id"]}/': site.home(category) for category in categories})
    if DIST.exists():
        shutil.rmtree(DIST)
    shutil.copytree(ROOT / 'site/assets', DIST / 'assets')
    for name in ('catalog.js', 'design.css', 'favicon.svg'):
        (DIST / 'assets' / name).write_bytes((ROOT / 'site/assets' / name).read_text(encoding='utf8').encode('utf8'))
    for path, content in pages.items():
        destination = DIST / (path.lstrip('/') if path.endswith('.html') else path.lstrip('/') + 'index.html')
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(content.encode('utf8'))
    ET.register_namespace('', 'http://www.sitemaps.org/schemas/sitemap/0.9')
    sitemap = ET.Element('{http://www.sitemaps.org/schemas/sitemap/0.9}urlset')
    for path in pages:
        if path != '/404.html':
            entry = ET.SubElement(sitemap, 'url')
            ET.SubElement(entry, 'loc').text = BASE + path
    (DIST / 'sitemap.xml').write_bytes(ET.tostring(sitemap, encoding='utf-8', xml_declaration=True))
    (DIST / 'robots.txt').write_text(f'User-agent: *\nAllow: /\nSitemap: {BASE}/sitemap.xml\n', encoding='utf8', newline='\n')
    (DIST / '_headers').write_text('''/*
  X-Content-Type-Options: nosniff
  Referrer-Policy: strict-origin-when-cross-origin
  Permissions-Policy: camera=(), microphone=(), geolocation=()
  Content-Security-Policy: default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self'; font-src 'self'; connect-src 'none'; object-src 'none'; base-uri 'none'; form-action 'self'; frame-ancestors 'none'
/assets/*
  Cache-Control: public, max-age=3600, must-revalidate
''', encoding='utf8', newline='\n')
    from check import SiteCheck
    report = SiteCheck(DIST, catalog, BASE + '/').run(ROOT / 'site/discovery.json')
    if not report['ok']:
        raise ValueError('Generated site failed validation:\n' + '\n'.join(report['errors']))
    print(f'Built {len(catalog)} tool pages, {len(active)} active tools and {len(categories)} categories')
    print(f'Checked {report["local_links_checked"]} local links and {report["images_checked"]} images')


if __name__ == '__main__':
    main()
