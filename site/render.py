"""HTML views for the software directory."""
from __future__ import annotations
import html
import hashlib
import re
import struct
from pathlib import Path
from urllib.parse import quote

BASE = 'https://kiwi-garakuta.pages.dev'
ROOT = Path(__file__).resolve().parents[1]


def asset_url(name):
    path = ROOT / 'site/assets' / name
    return f'/assets/{name}?v={hashlib.sha256(path.read_bytes()).hexdigest()[:12]}'


def esc(value):
    return html.escape(str(value), quote=True)


def icon(name, extra=''):
    shapes = {
        'image': '<rect x="3" y="3" width="18" height="18" rx="3"/><circle cx="8" cy="8" r="1.5"/><path d="m3 17 5-5 4 4 4-6 5 7"/>',
        'media': '<rect x="3" y="4" width="18" height="16" rx="3"/><path d="m10 8 6 4-6 4Z"/>',
        'document': '<path d="M14 3H6a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V9Z"/><path d="M14 3v6h6M8 13h8M8 17h5"/>',
        'files': '<path d="M3 7V5a2 2 0 0 1 2-2h5l3 3h6a2 2 0 0 1 2 2v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2Z"/><path d="M3 9h18"/>',
        'pc': '<rect x="3" y="3" width="18" height="14" rx="2"/><path d="M8 21h8m-4-4v4M7 8h5m-5 4h9"/>',
        'text': '<path d="M4 5h16M12 5v15M7 20h10M4 10V5m16 5V5"/>',
        'development': '<path d="m8 5-6 7 6 7m8-14 6 7-6 7m-3-17-2 20"/>',
        'search': '<circle cx="10.5" cy="10.5" r="7"/><path d="m16 16 5 5"/>',
        'download': '<path d="M12 3v12m-5-5 5 5 5-5M4 16v5h16v-5"/>',
        'arrow': '<path d="M4 12h16m-6-6 6 6-6 6"/>',
        'check': '<path d="m5 12 4 4L19 6"/>',
    }
    return f'<svg class="icon {esc(extra)}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">{shapes.get(name, shapes["files"])}</svg>'


def image_size(src):
    data = (ROOT / 'site' / src.lstrip('/')).read_bytes()
    if data[:8] == b'\x89PNG\r\n\x1a\n':
        return struct.unpack('>II', data[16:24])
    if data[:2] == b'\xff\xd8':
        offset = 2
        while offset < len(data):
            if data[offset] != 255:
                raise ValueError('Invalid JPEG marker')
            while data[offset] == 255:
                offset += 1
            marker = data[offset]
            offset += 1
            if marker in (0xD8, 0xD9) or 0xD0 <= marker <= 0xD7:
                continue
            size = int.from_bytes(data[offset:offset+2], 'big')
            if marker in (0xC0, 0xC1, 0xC2):
                height, width = struct.unpack('>HH', data[offset+3:offset+7])
                return width, height
            if size < 2:
                break
            offset += size
    raise ValueError(f'Unsupported screenshot format: {src}')


def image(src, alt, *, css='', lazy=True):
    width, height = image_size(src)
    loading = 'loading="lazy"' if lazy else 'fetchpriority="high"'
    return f'<img class="{esc(css)}" src="{esc(src)}" alt="{esc(alt)}" width="{width}" height="{height}" {loading} decoding="async">'


def notice_paragraphs(text):
    paragraphs, current = [], ''
    for sentence in re.findall(r'[^。]+。|[^。]+$', text):
        if current and len(current) + len(sentence) > 220:
            paragraphs.append(current)
            current = ''
        current += sentence
    if current:
        paragraphs.append(current)
    return ''.join(f'<p>{esc(p)}</p>' for p in paragraphs)


class Site:
    def __init__(self, settings, support, catalog, discovery):
        self.settings, self.support, self.catalog, self.discovery = settings, support, catalog, discovery
        self.tools = {t['slug']: t for t in catalog}
        self.active = [t for t in catalog if not t.get('replaced_by')]
        self.meta = discovery['tools']
        self.categories = {c['id']: c for c in discovery['categories']}
        featured = [f['slug'] for f in discovery['featured']]
        self.order = {slug: i for i, slug in enumerate(featured + [t['slug'] for t in self.active if t['slug'] not in featured])}

    def socials(self):
        return f'<div class="social-links"><a href="{esc(self.settings["contact_url"])}" rel="noopener noreferrer">X（Twitter） ↗</a><a href="{esc(self.settings["youtube_url"])}" rel="noopener noreferrer">YouTube ↗</a></div>'

    def page(self, title, description, body, path, *, catalog=False):
        full_title = self.settings['site_name'] if path == '/' else title + ' | ' + self.settings['site_name']
        script = f'<script src="{asset_url("catalog.js")}" defer></script>' if catalog else ''
        robots = '<meta name="robots" content="noindex">' if path == '/404.html' else ''
        tool_slug = path.removeprefix('/tools/').strip('/')
        share_image = self.tools[tool_slug]['screenshot'] if tool_slug in self.tools else '/assets/screenshots/kiwi-image-workbench-public.png'
        share_width, share_height = image_size(share_image)
        return f'''<!doctype html>
<html lang="ja"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="description" content="{esc(description)}"><title>{esc(full_title)}</title>
<link rel="canonical" href="{BASE}{esc(path)}"><meta property="og:type" content="website">
<meta property="og:locale" content="ja_JP"><meta property="og:site_name" content="{esc(self.settings['site_name'])}">
<meta property="og:title" content="{esc(full_title)}"><meta property="og:description" content="{esc(description)}"><meta property="og:url" content="{BASE}{esc(path)}">
<meta property="og:image" content="{BASE}{esc(share_image)}"><meta property="og:image:width" content="{share_width}"><meta property="og:image:height" content="{share_height}"><meta property="og:image:alt" content="{esc(title)}の動作画面"><meta name="twitter:card" content="summary_large_image">
<link rel="icon" href="/assets/favicon.svg" type="image/svg+xml"><link rel="stylesheet" href="{asset_url('design.css')}">{robots}{script}</head>
<body><a class="skip-link" href="#main">本文へ移動</a>
<header class="site-header"><div class="wrap header-inner"><a class="brand" href="/" aria-label="きういのガラクタ置き場 ホーム"><img src="/assets/favicon.svg" width="36" height="36" alt=""><span>きういの<span class="brand-break">ガラクタ置き場</span></span></a>
<nav class="main-nav" aria-label="メインメニュー"><a href="/#software">ソフト一覧</a><a href="/guide/">はじめての方へ</a><a href="/#about">きういについて</a></nav></div></header>
<main id="main" class="wrap" tabindex="-1">{body}</main>
<footer class="site-footer"><div class="wrap footer-grid"><div><a class="footer-brand" href="/">{esc(self.settings['site_name'])}</a><p>楽しく遊ぶための、小さな道具たち。<br>Windows向けの無料ソフトを公開しています。</p></div>
<nav aria-label="フッターメニュー"><a href="/#software">ソフトを探す</a><a href="/guide/">ダウンロード・使い始め方</a><a href="https://github.com/kiwidori/kiwi-garakuta" rel="noopener noreferrer">GitHub・ソースコード ↗</a></nav>
<div>{self.socials()}<p><a href="{esc(self.settings['contact_url'])}" rel="noopener noreferrer">お問い合わせはXのDMへ ↗</a></p></div></div>
<div class="wrap footer-bottom"><span>各ソフトのライセンスと出典は詳細ページに記載しています。</span><a href="#main">ページの先頭へ ↑</a></div></footer></body></html>'''

    def card(self, tool, *, order=0, category=None, filterable=False):
        slug = tool['slug']
        meta = self.meta[slug]
        cat = self.categories[meta['category']]
        data = ''
        if filterable:
            search = ' '.join([tool['name'], tool['summary'], cat['label'], *meta['tags'], *meta['keywords'], *meta['alias_names']])
            data = f'data-tool="{esc(slug)}" data-category="{cat["id"]}" data-search="{esc(search)}" data-name="{esc(tool["name"])}" data-order="{order}"'
        hidden = ' hidden' if category and cat['id'] != category else ''
        tags = ''.join(f'<span>{esc(tag)}</span>' for tag in meta['tags'])
        return f'''<article class="tool-card" {data}{hidden}>
<a href="/tools/{esc(slug)}/" class="card-link"><div class="card-screen">{image(tool['screenshot'], '', css='card-image')}<span class="screen-hint">実際の画面</span></div>
<div class="card-body"><div class="card-category">{icon(cat['id'])}{esc(cat['label'])}</div><h3>{esc(tool['name'])}</h3><p>{esc(tool['summary'])}</p><div class="tool-tags">{tags}</div><div class="card-bottom"><span>無料 · Windows 11</span><span class="card-more">詳細・ダウンロード {icon('arrow')}</span></div></div></a></article>'''

    def search(self, category=None):
        return f'''<form class="search-form" id="tool-search" action="/" method="get" role="search"><label for="search-input">やりたいこと・ソフト名で探す</label>
<div class="search-box">{icon('search')}<input id="search-input" name="q" type="search" maxlength="160" placeholder="例：PDF、写真、ファイルを送る" autocomplete="off" aria-describedby="search-help" disabled>
<button class="clear-query" id="clear-query" type="button" aria-label="検索語を消す" hidden>×</button><button class="button search-submit" type="submit" disabled>検索</button></div>
<p id="search-help" class="search-help">用途や、統合前のソフト名でも探せます。<span class="keyboard-hint"> <kbd>/</kbd> で検索へ</span></p><noscript><p class="search-help">キーワード検索にはJavaScriptが必要です。下のカテゴリからソフトを選べます。</p></noscript></form>'''

    def home(self, category=None):
        chosen = category['id'] if category else 'all'
        if category:
            hero = f'<nav class="crumb" aria-label="パンくず"><a href="/">ホーム</a><span>/</span><span>{esc(category["label"])}</span></nav><section class="category-hero"><div class="eyebrow">目的から選ぶ</div><h1>{esc(category["label"])}</h1><p class="lead">{esc(category["description"])}</p>{self.search(category)}</section>'
        else:
            picks = ''.join(f'<a class="quick-pick" href="/tools/{f["slug"]}/"><span class="pick-icon">{icon(self.meta[f["slug"]]["category"])}</span><span><strong>{esc(self.tools[f["slug"]]["name"].removeprefix("きうい"))}</strong><small>{esc(f["reason"])}</small></span>{icon("arrow")}</a>' for f in self.discovery['featured'])
            examples = ''.join(f'<a href="/?q={quote(term)}#software" data-search-example="{esc(term)}">{esc(term)}</a>' for term in ['写真', 'PDF', '文字起こし', 'ファイルを送る'])
            hero = f'''<section class="home-hero"><div class="hero-copy"><div class="eyebrow"><span class="status-dot"></span>無料のWindowsソフト · {len(self.active)}本公開中</div><h1>あの「ちょっと面倒」を、<br><em>ちょっと便利に。</em></h1><p class="lead">写真を整える。PDFをまとめる。ファイルを渡す。<br>日々の作業と遊びに役立つ、小さな道具を集めました。</p>{self.search()}<div class="search-examples"><span>たとえば</span>{examples}</div></div>
<aside class="quick-start" aria-label="まずはここから"><div class="section-kicker">まずはここから</div>{picks}<a class="guide-link" href="/guide/">はじめて使う方へ：ZIPの開き方 {icon('arrow')}</a></aside></section>'''
        counts = {c: sum(self.meta[t['slug']]['category'] == c for t in self.active) for c in self.categories}
        all_current = 'aria-current="true"' if chosen == 'all' else ''
        filters = f'<a href="/#software" data-filter="all" data-label="すべて" {all_current}>すべて <span>{len(self.active)}</span></a>'
        for cat in self.categories.values():
            current = 'aria-current="true"' if chosen == cat['id'] else ''
            filters += f'<a href="/categories/{cat["id"]}/#software" data-filter="{cat["id"]}" data-label="{esc(cat["label"])}" {current}>{icon(cat["id"])}{esc(cat["label"])} <span>{counts[cat["id"]]}</span></a>'
        cards = ''.join(self.card(t, order=self.order[t['slug']], category=None if chosen == 'all' else chosen, filterable=True) for t in sorted(self.active, key=lambda t: self.order[t['slug']]))
        count = len(self.active) if not category else counts[chosen]
        listing = f'''<section class="catalog-section" id="software" aria-labelledby="catalog-title"><nav class="category-filters" aria-label="ソフトのカテゴリ">{filters}</nav>
<div class="section-heading"><div><p class="section-kicker">道具を探す</p><h2 id="catalog-title">{esc(category['label']) if category else '公開中のソフト'}</h2><p id="result-count" role="status" aria-live="polite" aria-atomic="true">{len(self.active)}本中 {count}本を表示</p></div>
<div class="listing-options" data-js-only hidden><button id="reset-search" type="button" class="text-button" hidden>絞り込みを解除</button><label for="sort-tools">並び順</label><select id="sort-tools" aria-label="ソフトの並び順"><option value="recommended">おすすめ順</option><option value="name">名前順</option></select></div></div>
<div class="tool-grid" data-catalog data-category="{chosen}">{cards}</div><div class="no-results" id="no-results" hidden>{icon('search')}<h3>条件に合うソフトが見つかりませんでした</h3><p>短い言葉で探すか、カテゴリを「すべて」に変えてみてください。</p></div><noscript><p class="notice">カテゴリを選ぶと、その用途の一覧ページへ移動します。キーワード検索にはJavaScriptが必要です。</p></noscript></section>'''
        journeys = ''
        if not category:
            entries = ''
            for journey in self.discovery['journeys']:
                links = ''.join(f'<li><a href="/tools/{slug}/">{esc(self.tools[slug]["name"])} {icon("arrow")}</a></li>' for slug in journey['slugs'])
                entries += f'<article class="journey"><h3>{esc(journey["title"])}</h3><p>{esc(journey["description"])}</p><ol>{links}</ol></article>'
            journeys = f'<section class="workflow-section" aria-labelledby="workflow-title"><div class="section-heading"><div><p class="section-kicker">こんなときに</p><h2 id="workflow-title">やりたいことから、道具を選ぶ。</h2></div></div><div class="journey-grid">{entries}</div></section>'
        profile = f'''<section class="profile" id="about" aria-labelledby="profile-title"><div class="profile-heading"><img src="/assets/favicon.svg" alt="" width="64" height="64"><div><span class="section-kicker">このサイトの人</span><h2 id="profile-title">{esc(self.settings['profile_name'])}です。</h2></div></div><div><p>{esc(self.settings['profile_text'])}</p>{self.socials()}</div></section>'''
        description = f'{category["description"]}。Windows 11用の無料ソフトを用途から探せます。' if category else '写真・画像、PDF、動画、ファイル整理など、日々の作業に役立つWindows 11用の無料ソフト。用途やキーワードから探してダウンロードできます。'
        return self.page(category['label'] if category else self.settings['site_name'], description, hero + listing + journeys + profile, f'/categories/{chosen}/' if category else '/', catalog=True)

    def shot(self, src, caption, lazy=True):
        return f'<figure class="shot"><a href="{esc(src)}" aria-label="{esc(caption)}：原寸の画像を開く">{image(src, caption, lazy=lazy)}</a><figcaption>{esc(caption)} <span>· 画像を選ぶと原寸で表示</span></figcaption></figure>'

    def tool(self, tool):
        slug = tool['slug']
        active_slug = tool.get('replaced_by', slug)
        meta = self.meta[active_slug]
        cat = self.categories[meta['category']]
        version_match = re.search(r'/releases/download/[^/]*-v([0-9]+(?:\.[0-9]+)+)/', tool['download_url'])
        version = f'v{version_match[1]}' if version_match else 'ZIP版'
        filename = tool['download_url'].rsplit('/', 1)[-1]
        tags = ''.join(f'<span>{esc(t)}</span>' for t in meta['tags']) if not tool.get('replaced_by') else '<span>統合前の単体版</span>'
        replacement = ''
        if tool.get('replaced_by'):
            target = self.tools[active_slug]
            replacement = f'<aside class="replacement"><strong>この機能をまとめた統合版があります</strong><p>{esc(target["summary"])}</p><a class="button" href="/tools/{active_slug}/">{esc(target["name"])}を見る {icon("arrow")}</a><small>このページの単体版ZIPも引き続きダウンロードできます。</small></aside>'
        download_label = '単体版ZIPをダウンロード' if replacement else 'ZIPをダウンロード'
        preparation = next((s for s in tool['steps'] if '初回' in s), '')
        prep = f'<div class="preparation"><strong>初回の準備</strong><p>{esc(preparation)}</p></div>' if preparation else ''
        intro = f'''<nav class="crumb" aria-label="パンくず"><a href="/">ホーム</a><span>/</span><a href="/categories/{cat['id']}/">{esc(cat['label'])}</a><span>/</span><span>{esc(tool['name'])}</span></nav>{replacement}
<section class="tool-hero"><div><div class="eyebrow">{icon(cat['id'])}{esc(cat['label'])}</div><h1>{esc(tool['name'])}</h1><p class="lead">{esc(tool['summary'])}</p><div class="tool-tags">{tags}</div></div>
<aside class="download-panel" id="download" aria-label="ダウンロード"><div class="download-meta"><strong>無料</strong><span>{version}</span></div><p>Windows 11 x64 · ZIP版</p><a class="button download-button" href="{esc(tool['download_url'])}" rel="noopener noreferrer">{icon('download')}{download_label}</a><p class="filename">{esc(filename)}</p><a href="/guide/#start">ダウンロード後の使い方 {icon('arrow')}</a><small>ZIPをすべて展開してから起動してください。</small></aside></section>{prep}
<nav class="page-nav" aria-label="このページの内容"><a href="#features">できること</a><a href="#steps">使い方</a><a href="#screens">動作画面</a><a href="#notes">注意点</a><a href="#origin">出典・ソース</a></nav>'''
        features = ''.join(f'<li>{esc(value)}</li>' for value in tool['features'])
        steps = ''.join(f'<li><span>{esc(value)}</span></li>' for value in tool['steps'])
        shots = self.shot(tool['screenshot'], f'{tool["name"]}の実際の画面')
        shots += ''.join(self.shot(s['src'], s['caption']) for s in tool.get('workflow_screenshots', []))
        advanced = ''
        if tool.get('advanced_screenshot'):
            advanced = f'<section class="content-section" id="advanced"><h2>詳細機能</h2><p>メニュー「詳細機能」→「開く」で、元ツールの追加オプションを選択できます。値・ファイル・フォルダー・標準入力を指定して実行し、標準出力を保存できます。完全なCLI互換ではありません。</p><p><a href="https://github.com/kiwidori/kiwi-garakuta/blob/main/docs/upstream-feature-audit.md" rel="noopener noreferrer">対応する機能と制限の一覧 ↗</a></p>{self.shot(tool["advanced_screenshot"], tool["name"] + 'の詳細機能画面')}</section>'
        origins = tool.get('upstreams') or [{'name': '上流プロジェクト', 'url': tool['upstream_url'], 'license': tool['upstream_license']}]
        origins_html = ''.join(f'<li><a href="{esc(o["url"])}" rel="noopener noreferrer">{esc(o["name"])} ↗</a><p>ライセンス：{esc(o["license"])}</p></li>' for o in origins)
        models = ''.join(f'<li><a href="{esc(m["url"])}" rel="noopener noreferrer">{esc(m["name"])} ↗</a><p>モデルのライセンス：{esc(m["license"])}</p></li>' for m in tool.get('model_sources', []))
        source_download = f'<a href="{esc(tool["dependency_source_url"])}" rel="noopener noreferrer">元ツールの対応ソース ↗</a>' if tool.get('dependency_source_url') else ''
        # Keep the original notice intact; additional headings do not replace its details.
        content = f'''<div class="detail-layout"><div class="detail-main"><section class="content-section" id="features"><p class="section-kicker">できること</p><h2>このソフトでできること</h2><ul class="feature-list">{features}</ul></section>
<section class="content-section" id="steps"><p class="section-kicker">使い始める</p><h2>使い方</h2><ol class="steps">{steps}</ol><a class="guide-link" href="/guide/">ZIPの開き方や、起動できないときの案内 {icon('arrow')}</a></section>
<section class="content-section" id="screens"><p class="section-kicker">画面で確認</p><h2>実際の動作画面</h2>{shots}</section>{advanced}
<section class="content-section notes" id="notes"><p class="section-kicker">ダウンロード前に</p><h2>制限と注意点</h2><div class="notice-copy">{notice_paragraphs(tool['limitations'])}</div></section>
<section class="content-section origin" id="origin"><h2>出典・ソースコード</h2><ul>{origins_html}{models}</ul><p>本ソフトは上流プロジェクトの公式製品ではありません。</p><div class="source-links"><a href="{esc(tool['source_url'])}" rel="noopener noreferrer">このソフトのソースコード ↗</a>{source_download}</div></section></div>
<aside class="detail-aside"><div class="side-note"><strong>使い方で迷ったら</strong><p>ZIPの展開や初回の準備については、共通の使い方ガイドへ。</p><a href="/guide/">はじめての方へ {icon('arrow')}</a><hr><p>不具合や質問は、ソフト名と表示された内容を添えてXのDMへお寄せください。</p><a href="{esc(self.settings['contact_url'])}" rel="noopener noreferrer">@kiwi_dori ↗</a></div>{self.support_block()}</aside></div>'''
        others = [t for t in self.active if t['slug'] != active_slug and self.meta[t['slug']]['category'] == cat['id']]
        others.sort(key=lambda t: (-len(set(meta['tags']) & set(self.meta[t['slug']]['tags'])), self.order[t['slug']]))
        related = f'<section class="related-section"><div class="section-heading"><div><p class="section-kicker">こちらもどうぞ</p><h2>{esc(cat["label"])}の道具</h2></div><a href="/categories/{cat["id"]}/">このカテゴリをすべて見る →</a></div><div class="tool-grid">{"".join(self.card(t) for t in others[:3])}</div></section>' if others else ''
        amazon = ''
        if tool.get('amazon_links'):
            links = ''.join(f'<li><a href="{esc(l["url"])}" rel="sponsored noopener noreferrer">{esc(l["label"])} ↗</a></li>' for l in tool['amazon_links'])
            amazon = f'<section class="content-section"><h2>関連商品</h2><p>広告：ツールの利用に関連する商品を紹介しています。</p><ul>{links}</ul><p>Amazonのアソシエイトとして、{esc(self.settings["site_name"])}は適格販売により収入を得ています。</p></section>'
        download_again = f'<section class="download-again" aria-label="配布ファイル"><div><strong>{esc(tool["name"])}</strong><p>{version} · Windows 11 x64 · 無料ZIP</p></div><a class="button" href="{esc(tool["download_url"])}" rel="noopener noreferrer">{icon("download")}{download_label}</a></section>'
        return self.page(tool['name'], tool['summary'], intro + content + amazon + download_again + related, f'/tools/{slug}/')

    def support_block(self):
        paypal = self.support.get('paypal_url')
        if not paypal:
            return ''
        qr = self.support.get('paypal_qr')
        qr_html = f'<details><summary>QRコードを表示</summary><a href="{esc(paypal)}" rel="noopener noreferrer">{image(qr, "PayPal支援ページのQRコード", css="support-qr")}</a></details>' if qr else ''
        return f'<section class="support"><span class="section-kicker">気に入ってもらえたら</span><h2>開発を応援する</h2><p>ソフトは無料です。役に立ったときに、気軽に応援してもらえたらうれしいです。</p><a class="button button-secondary" href="{esc(paypal)}" rel="noopener noreferrer">PayPalで支援する ↗</a>{qr_html}</section>'

    def guide(self):
        body = f'''<nav class="crumb" aria-label="パンくず"><a href="/">ホーム</a><span>/</span><span>はじめての方へ</span></nav>
<section class="guide-hero"><div class="eyebrow">使い始める前に</div><h1>ダウンロードから、<br>最初のひと仕事まで。</h1><p class="lead">Windows 11 x64向けの無料ソフトです。<br>インストーラーを使わず、ZIPを展開して起動します。</p></section>
<nav class="page-nav" aria-label="ガイドの内容"><a href="#start">使い始め方</a><a href="#preparation">初回の準備</a><a href="#questions">よくある質問</a><a href="#contact">問い合わせ</a></nav>
<div class="guide-content"><section class="content-section" id="start"><h2>使い始めるには</h2><ol class="steps"><li><span><strong>目的に合うソフトを選ぶ</strong>詳細ページで「できること」「制限と注意点」を確認します。Windows 11 x64以外の環境は動作確認の対象外です。</span></li><li><span><strong>「ZIPをダウンロード」を選ぶ</strong>GitHub ReleasesからZIPが保存されます。GitHubの「Source code」は開発用で、実行ファイルのZIPとは異なります。</span></li><li><span><strong>ZIPをすべて展開する</strong>エクスプローラーでZIPを右クリックし「すべて展開」を選びます。中のファイルを一部だけ取り出さず、フォルダーごと保存してください。</span></li><li><span><strong>展開先の .exe を起動する</strong>各ページの使い方に記載された実行ファイルを開きます。フォルダー内の付属ファイルもそのまま残します。</span></li><li><span><strong>必要に応じて初回の準備をする</strong>処理エンジンやモデルを別途取得するソフトがあります。画面の案内と各ソフトの説明を確認し、小さなファイルで試してみてください。</span></li></ol></section>
<section class="content-section" id="preparation"><h2>初回の準備・対応環境</h2><div class="guide-points"><article><h3>追加ダウンロードがあるもの</h3><p>公式の処理エンジンやモデルを、初回に取得するソフトがあります。通信・空き容量が必要です。モデルのサイズや、準備後も通信する機能は個別ページで確認できます。</p></article><article><h3>追加の動作条件があるもの</h3><p>GPUやランタイムが必要なソフトもあります。ZIPを入手する前に「制限と注意点」を確認してください。</p></article><article><h3>起動時の警告について</h3><p>配布するZIPには、署名のない実行ファイルを含むものがあります。Windowsが警告を表示した場合は、入手先とファイル名、警告内容を確認してください。不明な場合は実行を止め、問い合わせてください。</p></article></div></section>
<section class="content-section faq" id="questions"><h2>よくある質問</h2><details><summary>本当に無料ですか？</summary><p>ここで公開しているソフトは無料でダウンロードできます。PayPalからの開発支援は任意です。各ソフトや元ツールのライセンスは詳細ページ・同梱文書に記載しています。</p></details><details><summary>ファイルをインターネットに送信しますか？</summary><p>機能によって異なります。PC内で処理するものも、動画・字幕の取得やファイル転送で通信するものもあります。個別ページの機能説明と注意点を確認してください。</p></details><details><summary>新しい版に入れ替えるには？</summary><p>新しいZIPを別フォルダーに展開して試してください。処理エンジン・モデル・設定・保存データの場所はソフトごとに異なるため、古いフォルダーを削除する前に確認してください。</p></details><details><summary>前にあったソフトが一覧にありません</summary><p>似た用途のソフトをまとめている場合があります。一覧で以前の名前を検索すると、統合先が見つかります。以前の詳細ページやZIPへのリンクも残しています。</p></details><details><summary>スマホやMacで動きますか？</summary><p>配布する実行ファイルはWindows 11 x64向けです。一部にはスマホのブラウザーと連携する機能がありますが、ソフト本体はWindows PCで起動します。</p></details></section>
<section class="content-section" id="contact"><h2>不具合や質問はこちら</h2><p>ソフト名・バージョン、行った操作、表示されたエラーを添えて、XのDMへお寄せください。画面を送る場合は、個人名・ファイルの内容・パスワードなどが写っていないか確認してください。</p><a class="button" href="{esc(self.settings['contact_url'])}" rel="noopener noreferrer">Xで @kiwi_dori を開く ↗</a></section><div class="back-catalog"><a href="/#software">{icon('arrow')}ソフト一覧へ戻る</a></div></div>'''
        return self.page('はじめての方へ', '無料Windowsソフトのダウンロード、ZIPの展開、初回の準備、起動時の確認について。', body, '/guide/')

    def not_found(self):
        return self.page('ページが見つかりません', '指定されたページが見つかりません。ソフト一覧からお探しください。', '<section class="guide-hero"><div class="eyebrow">404 · ページが見つかりません</div><h1>探している道具は、<br>こちらにあるかも。</h1><p class="lead">URLが変わったか、入力に誤りがあるようです。ソフト一覧からもう一度探してみてください。</p><a class="button" href="/#software">ソフト一覧へ</a><a class="textlink" href="/guide/">使い方ガイドへ</a></section>', '/404.html')
