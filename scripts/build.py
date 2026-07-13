#!/usr/bin/env python3
"""Builds docs/*.html from content/*.html fragments + sitemap.json.

Each content/<slug>.html file is a body-only HTML fragment (headings,
paragraphs, lists, tables, callouts) transcribed from the source PDF.
This script wraps every fragment in the shared site template: skip link,
header, breadcrumb, sidebar site navigation, in-page contents (built from
the fragment's headings), prev/next pager, and footer.
"""
import json
import re
import html
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SITEMAP = json.loads((ROOT / "scripts" / "sitemap.json").read_text())
CONTENT_DIR = ROOT / "content"
DOCS_DIR = ROOT / "docs"

SOURCE_PDF_NAME = "en_301549v040100va.pdf"
DOC_LABEL = "ETSI EN 301 549 V4.1.0"

HEADING_RE = re.compile(r'<h([23])\s+id="([^"]+)"[^>]*>(.*?)</h\1>', re.IGNORECASE | re.DOTALL)
TAG_RE = re.compile(r'<[^>]+>')


def strip_tags(s):
    return html.unescape(TAG_RE.sub('', s)).strip()


def build_page_toc(fragment_html):
    items = [(int(level), anchor_id, strip_tags(inner))
             for level, anchor_id, inner in HEADING_RE.findall(fragment_html)]
    if not items:
        return ""
    html_parts = ['<nav class="page-toc" aria-labelledby="page-toc-heading">',
                  '<h2 id="page-toc-heading">On this page</h2>', '<ol>']
    open_sub = False
    for i, (level, anchor_id, text) in enumerate(items):
        if level == 2:
            if open_sub:
                html_parts.append('</ol>')
                open_sub = False
            html_parts.append(f'<li><a href="#{anchor_id}">{html.escape(text)}</a>')
            # Determine if next item is a sub-item (h3); if not, close li now.
            nxt = items[i + 1] if i + 1 < len(items) else None
            if not (nxt and nxt[0] == 3):
                html_parts.append('</li>')
        else:
            if not open_sub:
                html_parts.append('<ol>')
                open_sub = True
            html_parts.append(f'<li><a href="#{anchor_id}">{html.escape(text)}</a></li>')
            nxt = items[i + 1] if i + 1 < len(items) else None
            if not (nxt and nxt[0] == 3):
                html_parts.append('</ol></li>')
                open_sub = False
    html_parts.append('</ol></nav>')
    return "\n".join(html_parts)


def build_site_nav(current_slug):
    groups = {}
    order = []
    for page in SITEMAP:
        g = page["group"]
        if not g:
            continue
        if g not in groups:
            groups[g] = []
            order.append(g)
        groups[g].append(page)

    parts = ['<nav class="site-nav" aria-labelledby="site-nav-heading">',
             '<h2 id="site-nav-heading">Contents</h2>']
    parts.append(f'<p><a href="index.html">Home</a></p>')
    for g in order:
        pages = groups[g]
        contains_current = any(p["slug"] == current_slug for p in pages)
        open_attr = " open" if contains_current else ""
        parts.append(f'<details{open_attr}><summary>{html.escape(g)}</summary><ul>')
        for p in pages:
            current = ' aria-current="page"' if p["slug"] == current_slug else ""
            parts.append(f'<li><a href="{p["slug"]}.html"{current}>{html.escape(p["shortTitle"])}</a></li>')
        parts.append('</ul></details>')
    parts.append('</nav>')
    return "\n".join(parts)


def build_breadcrumb(page):
    parts = ['<nav class="breadcrumb" aria-label="Breadcrumb"><div class="breadcrumb__inner"><ol>']
    parts.append('<li><a href="index.html">Home</a></li>')
    if page["group"]:
        parts.append(f'<li>{html.escape(page["group"])}</li>')
    parts.append(f'<li aria-current="page">{html.escape(page["shortTitle"])}</li>')
    parts.append('</ol></div></nav>')
    return "\n".join(parts)


def build_pager(index):
    prev_page = SITEMAP[index - 1] if index > 0 else None
    next_page = SITEMAP[index + 1] if index < len(SITEMAP) - 1 else None
    parts = ['<nav class="page-pager" aria-label="Page navigation">']
    if prev_page:
        parts.append(
            f'<a class="page-pager__link page-pager__link--prev" href="{prev_page["slug"]}.html">'
            f'<span class="page-pager__direction">&larr; Previous</span>'
            f'<span class="page-pager__title">{html.escape(prev_page["shortTitle"])}</span></a>'
        )
    else:
        parts.append('<span></span>')
    if next_page:
        parts.append(
            f'<a class="page-pager__link page-pager__link--next" href="{next_page["slug"]}.html">'
            f'<span class="page-pager__direction">Next &rarr;</span>'
            f'<span class="page-pager__title">{html.escape(next_page["shortTitle"])}</span></a>'
        )
    parts.append('</nav>')
    return "\n".join(parts)


PAGE_TEMPLATE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title} | {doc_label} Online</title>
<meta name="description" content="{description}">
<link rel="stylesheet" href="{asset_prefix}assets/css/style.css">
</head>
<body>
<a class="skip-link" href="#main-content">Skip to main content</a>

<header class="site-header">
  <div class="site-header__inner">
    <a class="site-header__title" href="{asset_prefix}index.html">
      {doc_label} Online
      <span class="site-header__subtitle">Accessibility requirements for ICT products and services</span>
    </a>
    <span class="site-header__doc-status">Final draft &middot; V4.1.0 (2026-06)</span>
  </div>
</header>

{breadcrumb}

<div class="page-shell{shell_modifier}">
  {site_nav}
  <main id="main-content">
    <div class="content">
      {content}
    </div>
    {pager}
  </main>
  {page_toc}
</div>

<footer class="site-footer">
  <div class="site-footer__inner">
    <p>This site republishes the text of <cite>{doc_label}: Accessibility requirements for ICT products and services</cite> as an accessible, WCAG 2.2 AA HTML edition. It is not an official ETSI publication.</p>
    <p>Source: <a href="https://www.etsi.org/deliver/etsi_en/301500_301599/301549/">ETSI EN 301 549 deliverables</a>. Original PDF: <a href="{asset_prefix}source/{source_pdf}">{source_pdf}</a>.</p>
  </div>
</footer>
</body>
</html>
"""


def render_page(index, page):
    slug = page["slug"]
    is_index = slug == "index"
    fragment_path = CONTENT_DIR / f"{slug}.html"
    if fragment_path.exists():
        fragment = fragment_path.read_text()
    else:
        fragment = f'<h1>{html.escape(page["title"])}</h1>\n<p><em>Not yet converted.</em></p>'

    page_toc_html = build_page_toc(fragment)
    shell_modifier = "" if page_toc_html else " page-shell--no-toc"

    html_out = PAGE_TEMPLATE.format(
        title=html.escape(page["title"]),
        doc_label=DOC_LABEL,
        description=html.escape(f'{page["title"]} — {DOC_LABEL} accessible HTML edition.'),
        asset_prefix="",
        breadcrumb="" if is_index else build_breadcrumb(page),
        shell_modifier=shell_modifier,
        site_nav=build_site_nav(slug),
        content=fragment,
        pager="" if is_index else build_pager(index),
        page_toc=page_toc_html,
        source_pdf=SOURCE_PDF_NAME,
    )
    out_path = DOCS_DIR / f"{slug}.html"
    out_path.write_text(html_out)
    return out_path


def main():
    built = []
    for i, page in enumerate(SITEMAP):
        built.append(render_page(i, page))
    print(f"Built {len(built)} pages into {DOCS_DIR}")


if __name__ == "__main__":
    main()
