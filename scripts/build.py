#!/usr/bin/env python3
"""Builds docs/*.html from content/*.html fragments + sitemap.json.

Each content/<slug>.html file is a body-only HTML fragment (headings,
paragraphs, lists, tables, callouts) transcribed from the source PDF.
This script wraps every fragment in the shared site template: skip link,
header, breadcrumb, a single left-hand contents sidebar (site-wide page
list, with the current page's own subsections nested inline under it),
prev/next pager, and footer.

The build validates its own output and exits with a non-zero status (and
no partial docs/ write) if it finds missing/extra content fragments,
duplicate IDs, a wrong number of <h1> elements, numbered headings whose
id doesn't match their clause number, skipped heading levels, broken
internal links, or invalid metadata. See validate() below for the full
list. Run with --check-only to run every validation without writing
docs/, e.g. to validate a change before committing it.
"""
import json
import re
import html
import sys
import calendar
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from heading_parser import parse_headings, canonical_id  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
SITEMAP_PATH = ROOT / "scripts" / "sitemap.json"
METADATA_PATH = ROOT / "data" / "source-metadata.json"
CLAUSE_SUMMARIES_PATH = ROOT / "data" / "clause-summaries.json"
CONTENT_DIR = ROOT / "content"
DOCS_DIR = ROOT / "docs"
SOURCE_PDF_PATH = ROOT / "docs" / "source" / "en_301549v040100va.pdf"

SOURCE_PDF_NAME = "en_301549v040100va.pdf"
DOC_LABEL = "ETSI EN 301 549 V4.1.0"

# Website-authored pages are not part of the reproduced standard, so they
# don't get a "Clause N"/"Annex X" source label in the page footer.
NON_STANDARD_SLUGS = {"index", "about", "accessibility-statement"}

# A page's own headings are listed in an "On this page" jump list once
# there are at least this many h2/h3 headings — short pages don't need one.
ON_THIS_PAGE_THRESHOLD = 4

# IDs the page template itself introduces; a content heading must not reuse
# one of these, or in-page anchors would become ambiguous.
RESERVED_IDS = {"main-content", "site-nav-panel", "status-live", "top",
                 "on-this-page-heading", "about-this-page"}

REQUIRED_METADATA_FIELDS = (
    "title", "version", "status", "statusHeadline", "statusBody",
    "sourceOrganisation", "sourcePdfUrl", "sourcePdfPublicationDate",
    "dateDownloaded", "statusLastChecked", "sha256",
)

TAG_RE = re.compile(r'<[^>]+>')
HREF_RE = re.compile(r'href="([^"]*)"')
PLACEHOLDER_RE = re.compile(r'\[insert[^\]]*\]', re.IGNORECASE)
VOID_TAGS = {"area", "base", "br", "col", "embed", "hr", "img", "input",
             "link", "meta", "param", "source", "track", "wbr"}


def strip_tags(s):
    return html.unescape(TAG_RE.sub('', s)).strip()


def human_date(iso):
    """'2026-07-13' -> '13 July 2026'; '2026-06' -> 'June 2026'. Day-month-
    year order throughout, matching New Zealand date conventions. Machine-
    readable ISO strings stay untouched everywhere except reader-facing text."""
    parts = iso.split("-")
    if len(parts) == 3:
        year, month, day = parts
        return f"{int(day)} {calendar.month_name[int(month)]} {year}"
    if len(parts) == 2:
        year, month = parts
        return f"{calendar.month_name[int(month)]} {year}"
    return iso


def human_page_range(pdf_pages):
    """'12' -> 'page 12'; '16-26' -> 'pages 16 to 26'."""
    if not pdf_pages:
        return ""
    if "-" in pdf_pages:
        start, end = pdf_pages.split("-", 1)
        return f"pages {start} to {end}"
    return f"page {pdf_pages}"


def source_pdf_size():
    if not SOURCE_PDF_PATH.exists():
        return None
    size_mb = SOURCE_PDF_PATH.stat().st_size / (1024 * 1024)
    return f"{size_mb:.1f} MB"


def substitute_tokens(fragment, metadata):
    """A handful of {{TOKEN}} placeholders content authors can use instead
    of hard-coding a value that build.py can compute reliably — so it can
    never go stale relative to data/source-metadata.json or the committed
    PDF. Not a general templating system: just these fixed tokens."""
    if not metadata:
        return fragment
    size = source_pdf_size()
    replacements = {
        "{{STATUS_LAST_CHECKED}}": human_date(metadata["statusLastChecked"]),
        "{{SOURCE_MONTH_YEAR}}": human_date(metadata["sourcePdfPublicationDate"]),
        "{{SOURCE_PDF_SIZE}}": f", {size}" if size else "",
    }
    for token, value in replacements.items():
        fragment = fragment.replace(token, value)
    return fragment


# ---------------------------------------------------------------------
# Error collection
# ---------------------------------------------------------------------

class Errors:
    def __init__(self):
        self.items = []

    def add(self, file, rule, message, fix):
        self.items.append((file, rule, message, fix))

    def __bool__(self):
        return bool(self.items)

    def report_and_exit(self):
        sys.stderr.write(f"\nBuild failed: {len(self.items)} validation error(s)\n\n")
        for file, rule, message, fix in self.items:
            sys.stderr.write(f"  {file}\n")
            sys.stderr.write(f"    rule:     {rule}\n")
            sys.stderr.write(f"    problem:  {message}\n")
            sys.stderr.write(f"    fix:      {fix}\n\n")
        sys.exit(1)


# ---------------------------------------------------------------------
# Metadata
# ---------------------------------------------------------------------

def load_metadata(errors):
    rel = METADATA_PATH.relative_to(ROOT)
    if not METADATA_PATH.exists():
        errors.add(str(rel), "metadata-missing",
                   "data/source-metadata.json does not exist.",
                   "Create data/source-metadata.json with the required fields "
                   "(see README's source metadata section).")
        return None
    raw = METADATA_PATH.read_text(encoding="utf-8")
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        errors.add(str(rel), "metadata-invalid-json",
                   f"Not valid JSON: {exc}",
                   f"Fix the syntax error at line {exc.lineno}, column {exc.colno}.")
        return None
    missing = [k for k in REQUIRED_METADATA_FIELDS if k not in data]
    if missing:
        errors.add(str(rel), "metadata-missing-fields",
                   f"Missing required field(s): {', '.join(missing)}",
                   f"Add {', '.join(missing)} to data/source-metadata.json.")
    return data


def load_clause_summaries(errors):
    """Plain-language 'About this clause/annex' orientation blurbs, keyed by
    slug. Kept as structured data rather than hard-coded in build.py so a
    non-developer can add or edit one without touching Python. A summary is
    optional per page — most pages have none, deliberately (see README)."""
    rel = CLAUSE_SUMMARIES_PATH.relative_to(ROOT)
    if not CLAUSE_SUMMARIES_PATH.exists():
        return {}
    raw = CLAUSE_SUMMARIES_PATH.read_text(encoding="utf-8")
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        errors.add(str(rel), "clause-summaries-invalid-json",
                   f"Not valid JSON: {exc}",
                   f"Fix the syntax error at line {exc.lineno}, column {exc.colno}.")
        return {}
    for slug, entry in data.items():
        if "heading" not in entry or "text" not in entry:
            errors.add(str(rel), "clause-summary-missing-fields",
                       f'The "{slug}" entry must have "heading" and "text" fields.',
                       'Add the missing field(s), e.g. "heading": "About this clause".')
    return data


# ---------------------------------------------------------------------
# Sitemap <-> content directory consistency
# ---------------------------------------------------------------------

def validate_sitemap_vs_content(errors):
    sitemap_slugs = {p["slug"] for p in SITEMAP}
    content_slugs = {p.stem for p in CONTENT_DIR.glob("*.html")}

    for slug in sorted(sitemap_slugs - content_slugs):
        errors.add(f"content/{slug}.html", "missing-content-fragment",
                   f"scripts/sitemap.json lists slug \"{slug}\" but content/{slug}.html does not exist.",
                   f"Create content/{slug}.html, or remove the \"{slug}\" entry from sitemap.json.")

    for slug in sorted(content_slugs - sitemap_slugs):
        errors.add(f"content/{slug}.html", "extra-content-fragment",
                   f"content/{slug}.html exists but no entry in scripts/sitemap.json points to it, "
                   "so it would never be built or linked from navigation.",
                   f"Add a \"{slug}\" entry to scripts/sitemap.json, or delete the file if it's unused.")


# ---------------------------------------------------------------------
# Per-fragment heading validation + permalink injection
# ---------------------------------------------------------------------

def validate_fragment_headings(slug, raw, headings, errors):
    label = f"content/{slug}.html"
    is_index = slug == "index"

    # The homepage has no template-level doc header, so its fragment must
    # supply the page's one <h1> itself. Every other page's <h1> comes from
    # build_doc_header() (sitemap.json's title), so its fragment must not
    # contain one at all — two <h1> elements would end up on the page.
    h1s = [h for h in headings if h.level == 1]
    if is_index:
        if len(h1s) != 1:
            errors.add(label, "h1-count",
                       f"Homepage fragment must contain exactly one <h1> (found {len(h1s)}); "
                       "it has no template-level doc header to supply one.",
                       "Give content/index.html exactly one <h1> as its first heading.")
        elif not h1s[0].text.strip():
            errors.add(label, "h1-empty", "The <h1> element has no visible text.",
                       "Give the <h1> real, non-empty text.")
        elif headings[0] is not h1s[0]:
            errors.add(label, "h1-not-first", "The <h1> is not the first heading in the fragment.",
                       "Move the <h1> to the top of content/index.html.")
    elif h1s:
        errors.add(label, "h1-in-fragment",
                   "This fragment contains its own <h1>, but the page template already "
                   "supplies the page's <h1> from sitemap.json's title. Two <h1> elements "
                   "would end up on the same generated page.",
                   f"Remove the <h1>...</h1> from {label} (run scripts/normalize_content.py), "
                   "and if the fragment's heading text is more complete than sitemap.json's "
                   "title, update the title in scripts/sitemap.json instead.")

    seen_ids = {}
    last_level = 1  # virtual parent: the template's own <h1> (or fragment h1 for index)
    for h in headings:
        if h.level == 1:
            continue
        if h.level > last_level + 1:
            errors.add(label, "heading-hierarchy-skip",
                       f'Heading "{h.text}" is <h{h.level}>, skipping directly after a level-{last_level} '
                       "heading with no level in between.",
                       f"Use <h{last_level + 1}> here, or add the missing intermediate heading level.")
        last_level = h.level

        if h.level in (2, 3) and not (h.id and h.id.strip()):
            errors.add(label, "heading-missing-id",
                       f'Heading "{h.text}" (<h{h.level}>) has no id attribute. The contents '
                       "sidebar and any direct link to this heading depend on it having one.",
                       f'Add id="..." to this heading (see scripts/normalize_content.py for the '
                       "numbered-heading convention).")

        if h.number:
            expected = canonical_id(h.number)
            if h.id != expected:
                errors.add(label, "heading-id-mismatch",
                           f'Numbered heading "{h.text}" has id="{h.id}", but the id for a numbered '
                           f'heading must be generated from its clause number, not its wording: expected id="{expected}".',
                           f'Set id="{expected}" on this heading, or run scripts/normalize_content.py '
                           "to fix every heading in the file at once.")
                expected_key = expected
            else:
                expected_key = h.id
            if expected_key in seen_ids:
                errors.add(label, "duplicate-id",
                           f'id="{expected_key}" is used by more than one heading on this page '
                           f'(first: "{seen_ids[expected_key]}", again: "{h.text}").',
                           "Give each heading a unique clause number, or fix the duplicated source numbering.")
            else:
                seen_ids[expected_key] = h.text
        elif h.id:
            if h.id in seen_ids:
                errors.add(label, "duplicate-id",
                           f'id="{h.id}" is used by more than one heading on this page '
                           f'(first: "{seen_ids[h.id]}", again: "{h.text}").',
                           "Give one of the two headings a different, unique id.")
            else:
                seen_ids[h.id] = h.text
            if h.id in RESERVED_IDS:
                errors.add(label, "reserved-id",
                           f'Heading "{h.text}" uses id="{h.id}", which is reserved for the page '
                           "template's own elements (main content landmark, nav panel, live region).",
                           "Choose a different id for this heading.")


def inject_permalinks(raw, headings):
    """Insert a small, always-visible permalink control just inside the
    closing tag of every numbered heading. Uses the same byte offsets
    heading_parser.py already computed, so this never touches heading
    text or attributes — only adds a trailing inline anchor."""
    edits = []
    for h in headings:
        if not h.number:
            continue
        anchor_id = h.id or canonical_id(h.number)
        label = html.escape(f"Copy link to {h.text}", quote=True)
        markup = (
            f' <a class="heading-permalink" href="#{anchor_id}" data-copy-link'
            f' aria-label="{label}"><span aria-hidden="true">#</span></a>'
        )
        edits.append((h.end, h.end, markup))
    edits.sort(key=lambda e: e[0], reverse=True)
    out = raw
    for start, end, replacement in edits:
        out = out[:start] + replacement + out[end:]
    return out


# ---------------------------------------------------------------------
# HTML tag-balance check (catches malformed/unclosed/mismatched markup)
# ---------------------------------------------------------------------

def check_tag_balance(label, html_text, errors):
    from html.parser import HTMLParser

    class BalanceChecker(HTMLParser):
        def __init__(self):
            super().__init__(convert_charrefs=True)
            self.stack = []

        def handle_starttag(self, tag, attrs):
            if tag not in VOID_TAGS:
                self.stack.append((tag, self.getpos()))

        def handle_startendtag(self, tag, attrs):
            pass  # explicitly self-closed; never pushed, nothing to balance

        def handle_endtag(self, tag):
            if not self.stack:
                errors.add(label, "malformed-html",
                           f"Closing tag </{tag}> at line {self.getpos()[0]} has no matching open tag.",
                           f"Remove the stray </{tag}>, or add the missing opening <{tag}>.")
                return
            open_tag, pos = self.stack[-1]
            if open_tag == tag:
                self.stack.pop()
                return
            # tolerate out-of-order close by searching the stack once
            for i in range(len(self.stack) - 1, -1, -1):
                if self.stack[i][0] == tag:
                    unclosed = self.stack[i + 1:]
                    for t, p in unclosed:
                        errors.add(label, "malformed-html",
                                   f"<{t}> opened at line {p[0]} is never closed before </{tag}> at line {self.getpos()[0]}.",
                                   f"Add the missing </{t}>, or check tag nesting near line {p[0]}.")
                    del self.stack[i:]
                    return
            errors.add(label, "malformed-html",
                       f"Closing tag </{tag}> at line {self.getpos()[0]} has no matching open tag.",
                       f"Remove the stray </{tag}>, or add the missing opening <{tag}>.")

    checker = BalanceChecker()
    checker.feed(html_text)
    checker.close()
    for tag, pos in checker.stack:
        errors.add(label, "malformed-html",
                   f"<{tag}> opened at line {pos[0]} is never closed.",
                   f"Add the missing </{tag}>.")


# ---------------------------------------------------------------------
# Template
# ---------------------------------------------------------------------

def build_subsection_tree(headings):
    """Nested <ul> of a page's own h2/h3 headings, for inlining under that
    page's entry in the left contents sidebar. Requirement-level (h4)
    headings are deliberately excluded — every one already has a stable,
    linkable id and an in-content permalink, but listing all of them in
    the site-wide sidebar would make it unusably long."""
    subsections = [h for h in headings if h.level in (2, 3)]
    if not subsections:
        return ""
    html_parts = ['<ul class="site-nav__subsections">']
    open_sub = False
    for i, h in enumerate(subsections):
        nxt = subsections[i + 1] if i + 1 < len(subsections) else None
        if h.level == 2:
            if open_sub:
                html_parts.append('</ul>')
                open_sub = False
            html_parts.append(f'<li><a href="#{h.id}" data-subsection>{html.escape(h.text)}</a>')
            if not (nxt and nxt.level == 3):
                html_parts.append('</li>')
        else:
            if not open_sub:
                html_parts.append('<ul class="site-nav__subsections site-nav__subsections--nested">')
                open_sub = True
            html_parts.append(f'<li><a href="#{h.id}" data-subsection>{html.escape(h.text)}</a></li>')
            if not (nxt and nxt.level == 3):
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
        </div>
        <h1>{html.escape(page["title"])}</h1>
      </div>
    </div>
    <div class="doc-toolbar" role="group" aria-label="Document actions">
      <button type="button" class="doc-toolbar__btn" data-action="print">Print</button>
      <a class="doc-toolbar__btn" href="source/{SOURCE_PDF_NAME}" aria-label="Download the official ETSI standard as a PDF">Download PDF</a>
      <button type="button" class="doc-toolbar__btn" data-action="copy-link">
        <span class="doc-toolbar__btn-label">Copy link</span>
        <span class="doc-toolbar__btn-status" aria-hidden="true"></span>
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


def build_site_title(asset_prefix):
    """The masthead is always a plain link back to the homepage, on every
    page including the homepage itself — it identifies the site, not the
    page. The page's own <h1> is separate: the homepage's fragment supplies
    its own (see content/index.html), and every other page's comes from
    build_doc_header()."""
    subtitle = '<span class="site-header__subtitle">Accessibility requirements for ICT products and services</span>'
    return (f'<a class="site-header__title" href="{asset_prefix}index.html">'
            f'{DOC_LABEL} Online {subtitle}</a>')


PAGE_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title} | {doc_label} Online</title>
<meta name="description" content="{description}">
<link rel="stylesheet" href="{asset_prefix}assets/css/style.css">
</head>
<body>
<a class="skip-link" id="top" href="#main-content">Skip to main content</a>

<header class="site-header">
  <div class="site-header__inner">
    {site_title}
    <button type="button" class="toc-toggle" aria-expanded="false" aria-controls="site-nav-panel">Contents</button>
  </div>
</header>
<div class="accent-bar" aria-hidden="true"></div>

{doc_header}

<div class="page-shell">
  {site_nav}
  <main id="main-content" tabindex="-1">
    <p class="draft-notice"><strong>{status_headline}.</strong> {status_body} <a href="accessibility-statement.html">Accessibility statement</a>.</p>
    <div class="content">
      {content}
    </div>
    {doc_footer}
    {pager}
  </main>
</div>

<a class="back-to-top" href="#top">&uarr; Back to top</a>

<div id="status-live" class="visually-hidden" role="status" aria-live="polite"></div>

<footer class="site-footer">
  <div class="site-footer__inner">
    <p>Unofficial HTML edition of the {source_month_year} final draft. <a href="{asset_prefix}about.html">Read how this edition was produced</a>.</p>
  </div>
</footer>
<script src="{asset_prefix}assets/js/site.js"></script>
</body>
</html>
"""


def source_label(page):
    """'Clause 1' / 'Annex C.8' — derived from sitemap data, used in the
    plain-language "Source in the official PDF" line. None for website-
    authored pages that don't reproduce a specific part of the standard."""
    if page["slug"] in NON_STANDARD_SLUGS:
        return None
    if page["group"] == "Clauses":
        number = page["title"].split(" ", 1)[0]
        return f"Clause {number}"
    m = re.match(r"^(Annex\s+\S+)", page["title"])
    return m.group(1) if m else None


def build_doc_footer(page):
    pdf_pages = page.get("pdfPages")
    label = source_label(page)
    if label and pdf_pages:
        location_line = f"{html.escape(label)}, {human_page_range(pdf_pages)}"
    elif pdf_pages:
        location_line = f"{html.escape(page['title'])}, {human_page_range(pdf_pages)}"
    else:
        location_line = html.escape(page["title"])
    return f"""<div class="doc-footer">
  <div>
    <p class="doc-footer__label">Source in the official PDF</p>
    <p>{location_line}</p>
  </div>
  <div class="doc-footer__right">
    <p><a href="https://www.etsi.org/deliver/etsi_en/301500_301599/301549/">View this standard on the ETSI website</a></p>
    <p>&copy; ETSI 2026</p>
  </div>
</div>"""


def render_metadata_summary(metadata):
    """The information most readers actually want, in plain language and
    human dates — always visible, never behind the Technical provenance
    disclosure. See render_metadata_technical() for everything else."""
    def row(label, value):
        return f"<div><dt>{html.escape(label)}</dt><dd>{value}</dd></div>"

    rows = [
        row("Standard version", html.escape(metadata["version"])),
        row("Publication status", html.escape(metadata["status"])),
        row("Source organisation", html.escape(metadata["sourceOrganisation"])),
        row("Source document", f'<a href="{html.escape(metadata["sourcePdfUrl"])}">View this standard on the ETSI website</a>'),
        row("Source date", human_date(metadata["sourcePdfPublicationDate"])),
        row("Date this edition was last checked against the source", human_date(metadata["statusLastChecked"])),
    ]
    return f'<dl class="content-meta-list">{"".join(rows)}</dl>'


def render_metadata_technical(metadata):
    """Implementation detail for maintainers verifying the source file,
    not something most readers need — kept in a native <details> disclosure
    so it's still reachable (and still readable with no JavaScript; details
    is a browser-native element) without competing with the summary above."""
    def row(label, value, note=None):
        note_html = f'<p class="content-meta">{html.escape(note)}</p>' if note else ""
        return f"<div><dt>{html.escape(label)}</dt><dd>{value}{note_html}</dd></div>"

    build_date = metadata.get("siteBuildDate")
    build_date_display = human_date(build_date) if build_date else "Not recorded"
    rows = [
        row("Machine-readable metadata file", "<code>data/source-metadata.json</code>"),
        row("Date downloaded", f'{human_date(metadata["dateDownloaded"])} ({html.escape(metadata["dateDownloaded"])})',
            metadata.get("dateDownloadedNote")),
        row("Source PDF SHA-256 checksum", f'<code>{html.escape(metadata["sha256"])}</code>', metadata.get("sha256Note")),
        row("Site build date", build_date_display, metadata.get("siteBuildDateNote") if not build_date else None),
    ]
    return (
        '<details class="technical-details">'
        '<summary>Technical provenance</summary>'
        '<p>These details are for anyone who wants to verify the source file directly '
        '(for example by re-running <code>sha256sum</code> against the committed PDF) '
        'rather than for everyday reading.</p>'
        f'<dl class="content-meta-list">{"".join(rows)}</dl>'
        '</details>'
    )


def build_on_this_page(headings):
    """A same-page contents list for pages long enough to need one,
    generated from the page's own h2/h3 headings (never the page's h1).
    Below ON_THIS_PAGE_THRESHOLD headings this returns nothing — a jump
    list with two entries isn't useful and just adds clutter."""
    subsections = [h for h in headings if h.level in (2, 3)]
    if len(subsections) < ON_THIS_PAGE_THRESHOLD:
        return ""
    parts = ['<nav class="on-this-page" aria-labelledby="on-this-page-heading">',
             '<h2 id="on-this-page-heading">On this page</h2>',
             '<ul>']
    open_sub = False
    for i, h in enumerate(subsections):
        nxt = subsections[i + 1] if i + 1 < len(subsections) else None
        if h.level == 2:
            if open_sub:
                parts.append('</ul>')
                open_sub = False
            parts.append(f'<li><a href="#{h.id}">{html.escape(h.text)}</a>')
            if not (nxt and nxt.level == 3):
                parts.append('</li>')
        else:
            if not open_sub:
                parts.append('<ul>')
                open_sub = True
            parts.append(f'<li><a href="#{h.id}">{html.escape(h.text)}</a></li>')
            if not (nxt and nxt.level == 3):
                parts.append('</ul></li>')
                open_sub = False
    parts.append('</ul></nav>')
    return "\n".join(parts)


NORMATIVE_LINK = '<a href="about.html#normative-and-informative">normative</a>'
INFORMATIVE_LINK = '<a href="about.html#normative-and-informative">informative</a>'


def build_clause_summary(slug, summaries, errors):
    """The short, clearly-labelled 'About this clause/annex' orientation
    block for the handful of pages listed in data/clause-summaries.json.
    Every summary ends with the same fixed sentence stating the content
    below is reproduced unchanged — see the critical constraint in
    README's content-authoring conventions."""
    entry = summaries.get(slug)
    if not entry:
        return ""
    label = f"data/clause-summaries.json ({slug})"
    paragraphs = []
    for para in entry["text"]:
        if "{{normative}}" in para and "{{informative}}" in para:
            errors.add(label, "clause-summary-ambiguous-link",
                       "A summary paragraph can link at most one of normative/informative.",
                       "Split into two paragraphs, or remove one of the placeholders.")
        text = para.replace("{{normative}}", NORMATIVE_LINK).replace("{{informative}}", INFORMATIVE_LINK)
        paragraphs.append(f"<p>{text}</p>")
    paragraphs.append("<p>The wording below is reproduced from the ETSI draft and has not been "
                       "simplified or changed.</p>")
    heading = html.escape(entry["heading"])
    return (
        '<div class="clause-summary">'
        f'<h2 id="about-this-page">{heading}</h2>'
        f'{"".join(paragraphs)}'
        '</div>'
    )


def render_page(index, page, metadata, summaries, errors):
    slug = page["slug"]
    is_index = slug == "index"
    fragment_path = CONTENT_DIR / f"{slug}.html"
    if not fragment_path.exists():
        return None  # already reported by validate_sitemap_vs_content

    fragment = fragment_path.read_text(encoding="utf-8")
    fragment = substitute_tokens(fragment, metadata)
    headings = parse_headings(fragment)
    validate_fragment_headings(slug, fragment, headings, errors)

    if slug == "about" and metadata:
        summary_marker = "<!-- SOURCE_METADATA_SUMMARY -->"
        technical_marker = "<!-- SOURCE_METADATA_TECHNICAL -->"
        for marker, name in ((summary_marker, "SOURCE_METADATA_SUMMARY"), (technical_marker, "SOURCE_METADATA_TECHNICAL")):
            if marker not in fragment:
                errors.add("content/about.html", "metadata-marker-missing",
                           f"content/about.html must contain the <!-- {name} --> marker.",
                           f"Add <!-- {name} --> where that metadata block should appear.")
        if summary_marker in fragment:
            fragment = fragment.replace(summary_marker, render_metadata_summary(metadata))
        if technical_marker in fragment:
            fragment = fragment.replace(technical_marker, render_metadata_technical(metadata))

    clause_summary = build_clause_summary(slug, summaries, errors)
    on_this_page = build_on_this_page(headings)
    fragment_html = inject_permalinks(fragment, headings)
    if is_index:
        # The homepage's <h1> lives inside the fragment itself (it has no
        # template-level doc header), so anything website-authored that
        # comes "before the content" must be spliced in after that <h1>,
        # not prepended in front of it — otherwise an <h2> would appear
        # before the page's only <h1> in document order. The <h1> is never
        # numbered, so it never gets a permalink inserted, meaning its
        # close_end offset is identical before and after inject_permalinks.
        split_at = headings[0].close_end
        content_html = fragment_html[:split_at] + clause_summary + on_this_page + fragment_html[split_at:]
    else:
        content_html = clause_summary + on_this_page + fragment_html

    html_out = PAGE_TEMPLATE.format(
        title=html.escape(page["title"]),
        doc_label=DOC_LABEL,
        description=html.escape(f'{page["title"]} — {DOC_LABEL} accessible HTML edition (final draft, under approval).'),
        asset_prefix="",
        site_title=build_site_title(""),
        doc_header="" if is_index else build_doc_header(page),
        status_headline=html.escape(metadata["statusHeadline"]) if metadata else "Final draft under approval",
        status_body=html.escape(metadata["statusBody"]) if metadata else "",
        source_month_year=human_date(metadata["sourcePdfPublicationDate"]) if metadata else "",
        site_nav=build_site_nav(slug, headings),
        content=content_html,
        doc_footer="" if is_index else build_doc_footer(page),
        pager="" if is_index else build_pager(index),
        source_pdf=SOURCE_PDF_NAME,
    )
    # Empty template placeholders (e.g. doc_header/pager on the homepage)
    # otherwise leave lines containing only the surrounding indentation.
    return "\n".join(line.rstrip() for line in html_out.split("\n"))


# ---------------------------------------------------------------------
# Whole-site, post-render validation
# ---------------------------------------------------------------------

def validate_rendered_page(slug, html_out, all_slugs, errors):
    label = f"docs/{slug}.html"

    h1_matches = re.findall(r'<h1[^>]*>(.*?)</h1>', html_out, re.IGNORECASE | re.DOTALL)
    if len(h1_matches) != 1:
        errors.add(label, "h1-count",
                   f"Generated page has {len(h1_matches)} <h1> element(s); every page must have exactly one.",
                   "Check build_doc_header()/PAGE_TEMPLATE and the fragment for content/%s.html." % slug)
    elif not strip_tags(h1_matches[0]):
        errors.add(label, "h1-empty", "The page's <h1> has no visible text.",
                   "Give the page a real title in scripts/sitemap.json.")

    ids = re.findall(r'\sid="([^"]+)"', html_out)
    seen = set()
    for i in ids:
        if i in seen:
            errors.add(label, "duplicate-id-rendered",
                       f'id="{i}" appears more than once in the fully rendered page.',
                       "Search the template and content fragment for a second element with this id.")
        seen.add(i)

    check_tag_balance(label, html_out, errors)

    for href in HREF_RE.findall(html_out):
        if href.startswith("#"):
            frag = href[1:]
            if frag and frag != "top" and frag not in seen:
                errors.add(label, "broken-anchor-link",
                           f'href="{href}" points to an id that does not exist on this page.',
                           f'Add id="{frag}" to the intended target, or fix the href.')
        elif href.startswith(("http://", "https://", "mailto:")):
            continue
        elif href.endswith(".html"):
            target_slug = href.rsplit("/", 1)[-1][:-5]
            if target_slug not in all_slugs:
                errors.add(label, "broken-internal-link",
                           f'href="{href}" does not match any page slug produced from scripts/sitemap.json.',
                           "Fix the href, or add the missing page to sitemap.json.")

    placeholder = PLACEHOLDER_RE.search(html_out)
    if placeholder:
        errors.add(label, "placeholder-text-published",
                   f'Unfilled placeholder text "{placeholder.group(0)}" would be published.',
                   "Replace the placeholder with real content, or remove it if none is available yet.")

    token = re.search(r'\{\{[A-Z_]+\}\}', html_out)
    if token:
        errors.add(label, "unreplaced-token",
                   f'Unreplaced template token "{token.group(0)}" would be published.',
                   "Check the token name matches one substitute_tokens() knows about, or that "
                   "data/source-metadata.json is present so tokens actually get substituted.")

    # NOTE: deliberately not scanning for raw ISO dates in reader-facing
    # text site-wide — Annex F's change-history table is reproduced ETSI
    # content containing ETSI's own process dates (e.g. "2025-11-13 to
    # 2026-02-11"), which must never be reformatted or flagged. Website-
    # authored dates are verified by inspection instead: everywhere this
    # build emits a date itself (draft notice, footer, metadata summary,
    # clause-summary/on-this-page text), it goes through human_date().

    for m in re.finditer(r'<a class="heading-permalink"[^>]*aria-label="([^"]*)"', html_out):
        name = html.unescape(m.group(1)).strip()
        if len(name) < len("Copy link to X"):
            errors.add(label, "permalink-accessible-name",
                       f'A heading permalink has an accessible name too short to be meaningful: "{name}".',
                       'Every heading permalink\'s aria-label must include both the heading number and text, '
                       'e.g. "Copy link to 9.1.1.1 Non-text content".')

    if slug == "accessibility-statement":
        if "github.com" not in html_out and "mailto:" not in html_out:
            errors.add(label, "accessibility-statement-no-reporting-route",
                       "The accessibility statement has no reporting link (expected a GitHub issues "
                       "link or a mailto: link).",
                       "Add a real reporting route — see content/accessibility-statement.html.")


# ---------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------

SITEMAP = json.loads(SITEMAP_PATH.read_text(encoding="utf-8"))


def main():
    check_only = "--check-only" in sys.argv
    errors = Errors()

    metadata = load_metadata(errors)
    summaries = load_clause_summaries(errors)
    validate_sitemap_vs_content(errors)

    if errors:
        errors.report_and_exit()

    rendered = {}
    for i, page in enumerate(SITEMAP):
        html_out = render_page(i, page, metadata, summaries, errors)
        if html_out is not None:
            rendered[page["slug"]] = html_out

    if errors:
        errors.report_and_exit()

    all_slugs = set(rendered.keys())
    for slug, html_out in rendered.items():
        validate_rendered_page(slug, html_out, all_slugs, errors)

    if errors:
        errors.report_and_exit()

    if check_only:
        print(f"Checked {len(rendered)} pages — no validation errors.")
        return

    DOCS_DIR.mkdir(exist_ok=True)
    for slug, html_out in rendered.items():
        (DOCS_DIR / f"{slug}.html").write_text(html_out, encoding="utf-8")

    print(f"Built {len(rendered)} pages into {DOCS_DIR}")


if __name__ == "__main__":
    main()
