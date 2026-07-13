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
import hashlib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from heading_parser import parse_headings, canonical_id  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
SITEMAP_PATH = ROOT / "scripts" / "sitemap.json"
METADATA_PATH = ROOT / "data" / "source-metadata.json"
CONTENT_DIR = ROOT / "content"
DOCS_DIR = ROOT / "docs"

SOURCE_PDF_NAME = "en_301549v040100va.pdf"
DOC_LABEL = "ETSI EN 301 549 V4.1.0"

# IDs the page template itself introduces; a content heading must not reuse
# one of these, or in-page anchors would become ambiguous.
RESERVED_IDS = {"main-content", "site-nav-panel", "status-live", "top"}

REQUIRED_METADATA_FIELDS = (
    "title", "version", "status", "draftNotice", "sourceOrganisation",
    "sourcePdfUrl", "sourcePdfPublicationDate", "dateDownloaded", "sha256",
)

TAG_RE = re.compile(r'<[^>]+>')
HREF_RE = re.compile(r'href="([^"]*)"')
VOID_TAGS = {"area", "base", "br", "col", "embed", "hr", "img", "input",
             "link", "meta", "param", "source", "track", "wbr"}


def strip_tags(s):
    return html.unescape(TAG_RE.sub('', s)).strip()


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
    else:
        if h1s:
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

    pdf_pages = page.get("pdfPages")
    meta_line = f"Source PDF p.{html.escape(pdf_pages)}" if pdf_pages else ""
    meta_html = f'<p class="doc-header__meta">{meta_line}</p>' if meta_line else ""

    return f"""<div class="doc-header">
  <div class="doc-header__inner">
    {"".join(breadcrumb)}
    <div class="doc-header__top">
      <div>
        <div class="doc-header__status-row">
          <span class="status-badge">Final draft</span>
        </div>
        <h1>{html.escape(page["title"])}</h1>
        {meta_html}
      </div>
    </div>
    <div class="doc-toolbar" role="group" aria-label="Document actions">
      <button type="button" class="doc-toolbar__btn" data-action="print">Print</button>
      <a class="doc-toolbar__btn" href="source/{SOURCE_PDF_NAME}">Download PDF</a>
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
    <p class="draft-notice"><strong>Draft under approval.</strong> {draft_notice_rest} <a href="accessibility-statement.html">Accessibility statement</a>.</p>
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
    <p>This site republishes the standard's text as an HTML edition, designed and tested with the aim of meeting WCAG 2.2 Level AA &mdash; see the <a href="{asset_prefix}accessibility-statement.html">accessibility statement</a> for what has and hasn't been verified. It is not an official ETSI publication, and this version of the standard is a final draft under approval, not yet published.</p>
    <p>Source: <a href="https://www.etsi.org/deliver/etsi_en/301500_301599/301549/">ETSI EN 301 549 deliverables</a>. Original PDF: <a href="{asset_prefix}source/{source_pdf}">{source_pdf}</a>.</p>
  </div>
</footer>
<script src="{asset_prefix}assets/js/site.js"></script>
</body>
</html>
"""


def build_doc_footer(page):
    pdf_pages = page.get("pdfPages")
    location_line = (f"{html.escape(page['title'])} &middot; source PDF p.{html.escape(pdf_pages)}"
                      if pdf_pages else html.escape(page["title"]))
    return f"""<div class="doc-footer">
  <div>
    <p class="doc-footer__label">Source</p>
    <p>{location_line}</p>
  </div>
  <div class="doc-footer__right">
    <p><a href="https://www.etsi.org/deliver/etsi_en/301500_301599/301549/">ETSI deliverable page</a></p>
    <p>&copy; ETSI 2026</p>
  </div>
</div>"""


def render_metadata_block(metadata):
    def row(label, value, note=None):
        note_html = f'<p class="content-meta">{html.escape(note)}</p>' if note else ""
        return f"<div><dt>{html.escape(label)}</dt><dd>{value}{note_html}</dd></div>"

    build_date = metadata.get("siteBuildDate") or "Not stamped"
    rows = [
        row("Title", html.escape(metadata["title"])),
        row("Version", html.escape(metadata["version"])),
        row("Status", html.escape(metadata["status"])),
        row("Source organisation", html.escape(metadata["sourceOrganisation"])),
        row("Source PDF", f'<a href="{html.escape(metadata["sourcePdfUrl"])}">{html.escape(metadata["sourcePdfUrl"])}</a>'),
        row("Source PDF publication date", html.escape(metadata["sourcePdfPublicationDate"]),
            metadata.get("sourcePdfPublicationDateNote")),
        row("Date downloaded", html.escape(metadata["dateDownloaded"]), metadata.get("dateDownloadedNote")),
        row("Source PDF SHA-256", f'<code>{html.escape(metadata["sha256"])}</code>', metadata.get("sha256Note")),
        row("Site build date", html.escape(build_date), metadata.get("siteBuildDateNote") if not metadata.get("siteBuildDate") else None),
    ]
    return f'<dl class="content-meta-list">{"".join(rows)}</dl>'


def render_page(index, page, metadata, errors):
    slug = page["slug"]
    is_index = slug == "index"
    fragment_path = CONTENT_DIR / f"{slug}.html"
    if not fragment_path.exists():
        return None  # already reported by validate_sitemap_vs_content

    fragment = fragment_path.read_text(encoding="utf-8")
    headings = parse_headings(fragment)
    validate_fragment_headings(slug, fragment, headings, errors)

    if slug == "about" and metadata:
        marker = "<!-- SOURCE_METADATA -->"
        if marker not in fragment:
            errors.add("content/about.html", "metadata-marker-missing",
                       "content/about.html must contain the <!-- SOURCE_METADATA --> marker "
                       "so the build can inject the source-metadata table.",
                       "Add <!-- SOURCE_METADATA --> where the metadata table should appear.")
        else:
            fragment = fragment.replace(marker, render_metadata_block(metadata))

    content_html = inject_permalinks(fragment, headings)

    draft_notice_rest = ""
    if metadata:
        full = metadata.get("draftNotice", "")
        draft_notice_rest = full.split("Draft under approval.", 1)[-1].strip()

    html_out = PAGE_TEMPLATE.format(
        title=html.escape(page["title"]),
        doc_label=DOC_LABEL,
        description=html.escape(f'{page["title"]} — {DOC_LABEL} accessible HTML edition (final draft, under approval).'),
        asset_prefix="",
        doc_header="" if is_index else build_doc_header(page),
        draft_notice_rest=html.escape(draft_notice_rest),
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


# ---------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------

SITEMAP = json.loads(SITEMAP_PATH.read_text(encoding="utf-8"))


def main():
    check_only = "--check-only" in sys.argv
    errors = Errors()

    metadata = load_metadata(errors)
    validate_sitemap_vs_content(errors)

    if errors:
        errors.report_and_exit()

    rendered = {}
    for i, page in enumerate(SITEMAP):
        html_out = render_page(i, page, metadata, errors)
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
