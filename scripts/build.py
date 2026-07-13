#!/usr/bin/env python3
"""Builds docs/*.html from content/*.html fragments + sitemap.json.

Each content/<slug>.html file is a body-only HTML fragment (headings,
paragraphs, lists, tables, callouts) transcribed from the source PDF.
This script wraps every fragment in the shared site template: skip link,
header, breadcrumb, a single left-hand contents sidebar (site-wide page
list, with the current page's own subsections nested inline under it),
prev/next pager, and footer.
"""
import json
import re
import html
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SITEMAP = json.loads((ROOT / "scripts" / "sitemap.json").read_text(encoding="utf-8"))
CONTENT_DIR = ROOT / "content"
DOCS_DIR = ROOT / "docs"

SOURCE_PDF_NAME = "en_301549v040100va.pdf"
DOC_LABEL = "ETSI EN 301 549 V4.1.0"

HEADING_RE = re.compile(r'<h([23])\s+id="([^"]+)"[^>]*>(.*?)</h\1>', re.IGNORECASE | re.DOTALL)
TAG_RE = re.compile(r'<[^>]+>')


def strip_tags(s):
    return html.unescape(TAG_RE.sub('', s)).strip()


def extract_headings(fragment_html):
    return [(int(level), anchor_id, strip_tags(inner))
            for level, anchor_id, inner in HEADING_RE.findall(fragment_html)]


def build_subsection_tree(headings):
    """Nested <ul> of a page's own h2/h3 headings, for inlining under that
    page's entry in the left contents sidebar (mirrors the reference
    mockup's Part -> section nesting, instead of a separate right column)."""
    if not headings:
        return ""
    html_parts = ['<ul class="site-nav__subsections">']
    open_sub = False
    for i, (level, anchor_id, text) in enumerate(headings):
        nxt = headings[i + 1] if i + 1 < len(headings) else None
        if level == 2:
            if open_sub:
                html_parts.append('</ul>')
                open_sub = False
            html_parts.append(f'<li><a href="#{anchor_id}" data-subsection>{html.escape(text)}</a>')
            if not (nxt and nxt[0] == 3):
                html_parts.append('</li>')
        else:
            if not open_sub:
                html_parts.append('<ul class="site-nav__subsections site-nav__subsections--nested">')
                open_sub = True
            html_parts.append(f'<li><a href="#{anchor_id}" data-subsection>{html.escape(text)}</a></li>')
            if not (nxt and nxt[0] == 3):
                html_parts.append('</ul></li>')
                open_sub = False
    html_parts.append('</ul>')
    return "\n".join(html_parts)


def build_site_nav(current_slug, current_headings):
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

    parts = ['<nav id="site-nav-panel" class="site-nav" aria-label="Site contents">',
             '<button type="button" class="site-nav__close" aria-label="Close table of contents">'
             '<span aria-hidden="true">Table of contents</span>'
             '<span aria-hidden="true">&times;</span></button>',
             '<div class="site-nav__header">Contents</div>']
    parts.append('<p><a href="index.html">Home</a></p>')
    for g in order:
        pages = groups[g]
        contains_current = any(p["slug"] == current_slug for p in pages)
        open_attr = " open" if contains_current else ""
        parts.append(f'<details{open_attr}><summary>{html.escape(g)}</summary><ul>')
        for p in pages:
            is_current = p["slug"] == current_slug
            current = ' aria-current="page"' if is_current else ""
            parts.append(f'<li><a href="{p["slug"]}.html"{current}>{html.escape(p["shortTitle"])}</a>')
            if is_current:
                parts.append(build_subsection_tree(current_headings))
            parts.append('</li>')
        parts.append('</ul></details>')
    parts.append('</nav>')
    return "\n".join(parts)


def build_doc_header(page):
    breadcrumb = ['<nav class="breadcrumb" aria-label="Breadcrumb"><ol>',
                  '<li><a href="index.html">Home</a></li>']
    if page["group"]:
        breadcrumb.append(f'<li>{html.escape(page["group"])}</li>')
    breadcrumb.append(f'<li aria-current="page">{html.escape(page["shortTitle"])}</li>')
    breadcrumb.append('</ol></nav>')

    return f"""<div class="doc-header">
  <div class="doc-header__inner">
    {"".join(breadcrumb)}
    <div class="doc-header__top">
      <div>
        <div class="doc-header__status-row">
          <span class="status-badge">Final draft</span>
          <span class="doc-header__eyebrow">{DOC_LABEL}</span>
        </div>
        <h1>{html.escape(page["title"])}</h1>
        <p class="doc-header__meta">{DOC_LABEL} (2026-06) &middot; source PDF p.{html.escape(page.get("pdfPages") or "")}</p>
      </div>
    </div>
    <div class="doc-toolbar" role="toolbar" aria-label="Document actions">
      <button type="button" class="doc-toolbar__btn" data-action="print">Print</button>
      <a class="doc-toolbar__btn" href="source/{SOURCE_PDF_NAME}">Download PDF</a>
      <button type="button" class="doc-toolbar__btn" data-action="copy-link">
        <span class="doc-toolbar__btn-label">Copy link</span>
      </button>
    </div>
  </div>
</div>"""


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
    <button type="button" class="toc-toggle" aria-expanded="false" aria-controls="site-nav-panel">Contents</button>
  </div>
</header>
<div class="accent-bar" aria-hidden="true"></div>

{doc_header}

<div class="page-shell">
  {site_nav}
  <main id="main-content" tabindex="-1">
    <div class="content">
      {content}
    </div>
    {doc_footer}
    {pager}
  </main>
</div>

<button type="button" class="back-to-top" aria-label="Back to top of page">&uarr; Back to top</button>

<footer class="site-footer">
  <div class="site-footer__inner">
    <p>This site republishes the text of <cite>{doc_label}: Accessibility requirements for ICT products and services</cite> as an accessible, WCAG 2.2 AA HTML edition. It is not an official ETSI publication.</p>
    <p>Source: <a href="https://www.etsi.org/deliver/etsi_en/301500_301599/301549/">ETSI EN 301 549 deliverables</a>. Original PDF: <a href="{asset_prefix}source/{source_pdf}">{source_pdf}</a>.</p>
  </div>
</footer>
<script src="{asset_prefix}assets/js/site.js"></script>
</body>
</html>
"""


def build_doc_footer(page):
    return f"""<div class="doc-footer">
  <div>
    <p class="doc-footer__label">Reprinted from</p>
    <p><cite>{DOC_LABEL}: Accessibility requirements for ICT products and services</cite></p>
    <p>{html.escape(page["title"])} &middot; source PDF p.{html.escape(page.get("pdfPages") or "")}</p>
  </div>
  <div class="doc-footer__right">
    <p><a href="https://www.etsi.org/deliver/etsi_en/301500_301599/301549/">ETSI deliverable page</a></p>
    <p>&copy; ETSI 2026</p>
  </div>
</div>"""


def render_page(index, page):
    slug = page["slug"]
    is_index = slug == "index"
    fragment_path = CONTENT_DIR / f"{slug}.html"
    if fragment_path.exists():
        fragment = fragment_path.read_text(encoding="utf-8")
    else:
        fragment = f'<h1>{html.escape(page["title"])}</h1>\n<p><em>Not yet converted.</em></p>'

    current_headings = extract_headings(fragment)

    html_out = PAGE_TEMPLATE.format(
        title=html.escape(page["title"]),
        doc_label=DOC_LABEL,
        description=html.escape(f'{page["title"]} — {DOC_LABEL} accessible HTML edition.'),
        asset_prefix="",
        doc_header="" if is_index else build_doc_header(page),
        site_nav=build_site_nav(slug, current_headings),
        content=fragment,
        doc_footer="" if is_index else build_doc_footer(page),
        pager="" if is_index else build_pager(index),
        source_pdf=SOURCE_PDF_NAME,
    )
    out_path = DOCS_DIR / f"{slug}.html"
    out_path.write_text(html_out, encoding="utf-8")
    return out_path


def main():
    built = []
    for i, page in enumerate(SITEMAP):
        built.append(render_page(i, page))
    print(f"Built {len(built)} pages into {DOCS_DIR}")


if __name__ == "__main__":
    main()
