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
import datetime
import hashlib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from heading_parser import parse_headings, canonical_id, parse_terms  # noqa: E402

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
NON_STANDARD_SLUGS = {"index", "about", "accessibility-statement", "search"}

# A page's own headings are listed in an "On this page" jump list once
# there are at least this many h2/h3 headings — short pages don't need one.
ON_THIS_PAGE_THRESHOLD = 4

# A page's <dt> definition-list terms get stable ids and (once there are
# enough of them to be worth it) an A-Z index once there are at least this
# many. This is deliberately a term-count threshold, not a hardcoded page
# slug: today only clause 3's 141-term glossary crosses it — the small
# 4-term "Key to Tables ... columns" legends elsewhere don't, and shouldn't.
AZ_INDEX_THRESHOLD = 20

# IDs the page template itself introduces; a content heading must not reuse
# one of these, or in-page anchors would become ambiguous.
RESERVED_IDS = {"main-content", "site-nav-panel", "status-live", "top",
                 "on-this-page-heading", "about-this-page"}

# Website-only headings that must never end up listed in the "On this page"
# jump list — that list is meant to help readers scan the reproduced ETSI
# section headings, not website scaffolding. Checked structurally at
# render time (build_on_this_page() is only ever fed the fragment's own
# parsed headings, never the injected clause-summary/on-this-page markup),
# and re-checked here on the final rendered output so a future refactor
# can't silently reintroduce this by accident.
UTILITY_HEADING_TEXTS = {"About this clause", "About this annex", "On this page",
                          "Source in the official PDF"}

REQUIRED_METADATA_FIELDS = (
    "title", "version", "status",
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


CSS_PATH = DOCS_DIR / "assets" / "css" / "style.css"
JS_PATH = DOCS_DIR / "assets" / "js" / "site.js"


def asset_version(path):
    """Short content hash appended as ?v=... to the shared CSS/JS URLs.
    GitHub Pages caches assets for ~10 minutes, so without this a style
    change rolls out unevenly — pages loaded at different moments mix old
    and new styling until every visitor's cache expires. With it, any
    change to the file changes every page's asset URL in the same build,
    so all pages pick up the new styles together. Content-derived, so a
    rebuild from unchanged source still produces byte-identical output
    (the reproducibility guarantee in the README holds). Note these two
    files are hand-authored source that happens to live under docs/
    (see README) — this does not read any *generated* output."""
    if not path.exists():
        return "0"
    return hashlib.sha256(path.read_bytes()).hexdigest()[:8]


def source_pdf_size(errors=None):
    """The download link's file size, computed from the PDF committed at
    docs/source/ — never downloaded or guessed, so the build works fully
    offline and the value can never silently go stale (it's recomputed
    every build from whatever file is actually there). If the file is
    missing, callers fall back to plain "(PDF)" wording with no size — see
    substitute_tokens(). A file that exists but is implausibly small is a
    real problem (a corrupted or truncated commit), not something to
    silently paper over, so that's a build error instead of a fallback."""
    if not SOURCE_PDF_PATH.exists():
        return None
    size_bytes = SOURCE_PDF_PATH.stat().st_size
    if size_bytes < 1024 and errors is not None:
        errors.add(str(SOURCE_PDF_PATH.relative_to(ROOT)), "source-pdf-implausible-size",
                   f"The committed source PDF is only {size_bytes} bytes — almost certainly "
                   "truncated or corrupted, not a real ETSI standard document.",
                   "Re-commit a complete copy of the source PDF.")
        return None
    size_mb = size_bytes / (1024 * 1024)
    return f"{size_mb:.1f} MB"


def substitute_tokens(fragment, metadata, errors):
    """A handful of {{TOKEN}} placeholders content authors can use instead
    of hard-coding a value that build.py can compute reliably — so it can
    never go stale relative to data/source-metadata.json or the committed
    PDF. Not a general templating system: just these fixed tokens."""
    if not metadata:
        return fragment
    size = source_pdf_size(errors)
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

# Dates that are almost certainly a leftover placeholder rather than a
# genuine check date — reject these outright rather than publish them.
PLACEHOLDER_DATES = {"0000-00-00", "1970-01-01", "1900-01-01", "9999-12-31", "0001-01-01"}


def validate_iso_date_field(field, data, errors, rel, allow_future=False):
    """Shared validation for a full YYYY-MM-DD field in source-metadata.json:
    present, syntactically valid, not an obvious placeholder, and (for
    statusLastChecked specifically) not in the future — a future check date
    can only mean the field was set mechanically rather than genuinely
    checked."""
    if field not in data:
        return  # already reported as a missing required field
    value = data[field]
    if not isinstance(value, str) or value in PLACEHOLDER_DATES:
        errors.add(rel, "metadata-date-placeholder",
                   f'"{field}" is "{value}", which looks like a placeholder rather than a real date.',
                   f'Set "{field}" to the actual date this was genuinely checked, in YYYY-MM-DD form.')
        return
    try:
        parsed = datetime.date.fromisoformat(value)
    except ValueError:
        errors.add(rel, "metadata-date-invalid",
                   f'"{field}" value "{value}" is not a valid ISO date (expected YYYY-MM-DD).',
                   f'Fix "{field}" in data/source-metadata.json to a real YYYY-MM-DD date.')
        return
    if not allow_future and parsed > datetime.date.today():
        errors.add(rel, "metadata-date-future",
                   f'"{field}" value "{value}" is in the future.',
                   f'"{field}" must be a date something was genuinely checked on — set it to today '
                   "or an earlier date, not a future one.")


def validate_source_pdf_checksum(data, errors, rel, pdf_path=SOURCE_PDF_PATH):
    """Validate the recorded checksum against the exact PDF being published."""
    expected_sha = data.get("sha256")
    if expected_sha is None:
        return
    if not isinstance(expected_sha, str) or not re.fullmatch(r"[0-9a-fA-F]{64}", expected_sha):
        errors.add(rel, "metadata-sha256-invalid",
                   '"sha256" must be exactly 64 hexadecimal characters.',
                   "Replace it with the SHA-256 checksum of the committed source PDF.")
    elif not pdf_path.exists():
        errors.add(str(pdf_path.relative_to(ROOT)) if pdf_path.is_relative_to(ROOT) else str(pdf_path),
                   "source-pdf-missing",
                   "The source PDF recorded by the metadata is missing.",
                   f"Commit the source PDF at {pdf_path}.")
    else:
        actual_sha = hashlib.sha256(pdf_path.read_bytes()).hexdigest()
        if actual_sha != expected_sha.lower():
            errors.add(rel, "metadata-sha256-mismatch",
                       'The recorded "sha256" does not match the committed source PDF.',
                       "Verify the PDF is the intended source, then update the checksum "
                       "only after independently recomputing it.")


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
    rel_str = str(rel)
    validate_iso_date_field("statusLastChecked", data, errors, rel_str)
    validate_iso_date_field("dateDownloaded", data, errors, rel_str)

    validate_source_pdf_checksum(data, errors, rel_str)
    return data


CLAUSE_SUMMARY_MAX_PARAGRAPHS = 2
CLAUSE_SUMMARY_MAX_PARAGRAPH_CHARS = 400
ALLOWED_SUMMARY_TOKENS = ("{{normative}}", "{{informative}}")


def _no_duplicate_keys(pairs):
    seen = {}
    for key, value in pairs:
        if key in seen:
            raise ValueError(f'duplicate key "{key}"')
        seen[key] = value
    return seen


def load_clause_summaries(errors):
    """Plain-language 'About this clause/annex' orientation blurbs, keyed by
    slug. Kept as structured data rather than hard-coded in build.py so a
    non-developer can add or edit one without touching Python. A summary is
    optional per page — most pages have none, deliberately (see README).
    Validated here rather than hand-reviewed only, since this data is meant
    to stay small and easy to extend without re-auditing the whole file by
    eye every time."""
    rel = str(CLAUSE_SUMMARIES_PATH.relative_to(ROOT))
    if not CLAUSE_SUMMARIES_PATH.exists():
        return {}
    raw = CLAUSE_SUMMARIES_PATH.read_text(encoding="utf-8")
    try:
        data = json.loads(raw, object_pairs_hook=_no_duplicate_keys)
    except (json.JSONDecodeError, ValueError) as exc:
        errors.add(rel, "clause-summaries-invalid-json",
                   f"Not valid JSON: {exc}",
                   "Fix the syntax error (or duplicate key) reported above.")
        return {}

    sitemap_slugs = {p["slug"] for p in SITEMAP}
    for slug, entry in data.items():
        label = f"{rel} ({slug})"

        if slug not in sitemap_slugs:
            errors.add(label, "clause-summary-unknown-page",
                       f'"{slug}" is not a page slug in scripts/sitemap.json.',
                       "Fix the slug, or remove this entry if the page no longer exists.")

        if "heading" not in entry or "text" not in entry:
            errors.add(label, "clause-summary-missing-fields",
                       "This entry must have \"heading\" and \"text\" fields.",
                       'Add the missing field(s), e.g. "heading": "About this clause".')
            continue

        if not isinstance(entry["heading"], str) or not entry["heading"].strip():
            errors.add(label, "clause-summary-empty-heading",
                       '"heading" is empty or not a string.',
                       'Give it real text, e.g. "About this clause" or "About this annex".')

        paragraphs = entry["text"]
        if not isinstance(paragraphs, list) or not paragraphs:
            errors.add(label, "clause-summary-empty",
                       '"text" must be a non-empty list of paragraph strings.',
                       "Add at least one paragraph.")
            continue

        if len(paragraphs) > CLAUSE_SUMMARY_MAX_PARAGRAPHS:
            errors.add(label, "clause-summary-too-long",
                       f'"text" has {len(paragraphs)} paragraphs; the limit is '
                       f"{CLAUSE_SUMMARY_MAX_PARAGRAPHS} (keep it short).",
                       "Trim this summary to at most two short paragraphs.")

        for i, para in enumerate(paragraphs):
            if not isinstance(para, str) or not para.strip():
                errors.add(label, "clause-summary-empty-paragraph",
                           f"Paragraph {i + 1} is empty or not a string.",
                           "Remove the empty entry, or give it real text.")
                continue
            if len(para) > CLAUSE_SUMMARY_MAX_PARAGRAPH_CHARS:
                errors.add(label, "clause-summary-paragraph-too-long",
                           f"Paragraph {i + 1} is {len(para)} characters; the limit is "
                           f"{CLAUSE_SUMMARY_MAX_PARAGRAPH_CHARS} (this is meant to be a short orientation, "
                           "not a full explanation).",
                           "Shorten this paragraph.")
            stripped_of_tokens = para
            for token in ALLOWED_SUMMARY_TOKENS:
                stripped_of_tokens = stripped_of_tokens.replace(token, "")
            if "<" in stripped_of_tokens or ">" in stripped_of_tokens:
                errors.add(label, "clause-summary-raw-html",
                           f"Paragraph {i + 1} contains a '<' or '>' character outside of the "
                           f"supported {{{{normative}}}}/{{{{informative}}}} tokens — raw HTML is not "
                           "supported in this file.",
                           "Write plain text only. Use {{normative}} or {{informative}} for the one "
                           "supported link, not a hand-written <a> tag.")
            if PLACEHOLDER_RE.search(para):
                errors.add(label, "clause-summary-placeholder",
                           f"Paragraph {i + 1} contains unfilled placeholder text.",
                           "Replace the placeholder with real content before this can be published.")
    return data


# ---------------------------------------------------------------------
# Content ownership / governance metadata (optional, never invented)
# ---------------------------------------------------------------------

CONTENT_OWNERSHIP_PATH = ROOT / "data" / "content-ownership.json"
CONTENT_OWNERSHIP_FIELDS = (
    "owner", "ownerRole", "lastReviewDate", "nextReviewDate",
    "reviewFrequency", "statusCheckDate",
)
_CONTENT_OWNERSHIP_DATE_FIELDS = ("lastReviewDate", "nextReviewDate", "statusCheckDate")


def load_content_ownership():
    """Optional per-page governance metadata (who owns this page's content,
    when it was last/next reviewed) for the site's website-authored pages.
    This file is entirely optional and every field within it is optional:
    real values are only ever added by a maintainer who actually knows
    them. Nothing here is invented, and a missing file or missing field
    never fails the build — see content_ownership_notices()."""
    if not CONTENT_OWNERSHIP_PATH.exists():
        return {}
    try:
        data = json.loads(CONTENT_OWNERSHIP_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def validate_content_ownership(ownership, errors):
    rel = str(CONTENT_OWNERSHIP_PATH.relative_to(ROOT))
    for slug, entry in ownership.items():
        label = f"{rel} ({slug})"
        if slug not in NON_STANDARD_SLUGS:
            errors.add(label, "content-ownership-unknown-slug",
                       f'"{slug}" is not one of this site\'s website-authored pages '
                       f'({", ".join(sorted(NON_STANDARD_SLUGS))}).',
                       "Fix the slug, or remove this entry if it doesn't apply.")
            continue
        if not isinstance(entry, dict):
            errors.add(label, "content-ownership-invalid-entry",
                       "This entry must be an object.",
                       "Use an object with the expected fields — see "
                       "docs-for-maintainers/content-ownership.md.")
            continue
        for field, value in entry.items():
            if field not in CONTENT_O…10778 tokens truncated…urn slug or "term"


def render_dt_starttag(attrs, term_id):
    parts = ["dt"]
    has_id = has_tabindex = False
    for k, v in attrs:
        if k == "id":
            parts.append(f'id="{term_id}"')
            has_id = True
        elif k == "tabindex":
            parts.append('tabindex="-1"')
            has_tabindex = True
        elif v is None:
            parts.append(k)
        else:
            parts.append(f'{k}="{v}"')
    if not has_id:
        parts.append(f'id="{term_id}"')
    if not has_tabindex:
        # Focusable-but-not-tabbable: lets site.js move keyboard focus to a
        # definition when its fragment link is followed (see site.js), while
        # never adding the term itself as an extra stop in normal Tab order.
        parts.append('tabindex="-1"')
    return "<" + " ".join(parts) + ">"


def assign_term_ids(fragment, terms):
    """Give every <dt> a stable, deterministic id (preserving one it already
    has) and tabindex="-1" so it can receive focus when linked to directly.
    Returns the updated fragment and the final (id, text) pairs in document
    order. Never touches the definitions' own text or their order."""
    edits = []
    seen = set()
    assigned = []
    for term in terms:
        if term.id:
            new_id = term.id
        else:
            base = f"def-{slugify_term(term.text)}"
            new_id = base
            n = 2
            while new_id in seen:
                new_id = f"{base}-{n}"
                n += 1
        seen.add(new_id)
        assigned.append((new_id, term.text))
        edits.append((term.start, term.tag_end, render_dt_starttag(term.attrs, new_id)))
    edits.sort(key=lambda e: e[0], reverse=True)
    out = fragment
    for start, end, replacement in edits:
        out = out[:start] + replacement + out[end:]
    return out, assigned


def find_dl_spans(fragment):
    """Locate every <dl>...</dl> span. Clause 3 has two: the 3.1 Terms list
    and the 3.3 Abbreviations list. Definition lists are never nested in
    this content, so a simple non-nested scan is sufficient."""
    spans = []
    pos = 0
    while True:
        start = fragment.find("<dl>", pos)
        if start == -1:
            break
        end = fragment.find("</dl>", start)
        if end == -1:
            break
        end += len("</dl>")
        spans.append((start, end))
        pos = end
    return spans


def build_az_index(assigned_terms, index_id, aria_label):
    """A same-page A-Z index: one link per letter that's actually present,
    each pointing at the first term starting with that letter. Only letters
    with at least one term appear — no disabled-looking dead letters. Uses
    aria-label rather than a heading, so it never becomes an extra entry in
    the page's own heading structure (on-this-page, sidebar nav, permalinks).
    aria_label must be unique per page (html-validate's unique-landmark
    rule) whenever a page has more than one A-Z index."""
    first_seen = {}
    for term_id, text in assigned_terms:
        letter = text[0].upper() if text and text[0].isalpha() else "#"
        if letter not in first_seen:
            first_seen[letter] = term_id
    letters = sorted(first_seen.keys())
    links = "".join(
        f'<li><a href="#{first_seen[letter]}">{letter}'
        f'<span class="visually-hidden"> (jump to terms starting with {letter})</span></a></li>'
        for letter in letters
    )
    return (
        f'<nav class="az-index" aria-label="{html.escape(aria_label)}" id="{index_id}">'
        f'<ul>{links}</ul>'
        '</nav>'
    )


def apply_glossary_terms(fragment, errors, label):
    """Give every <dt> definition a stable id (and tabindex="-1") and, for
    each <dl> with enough terms to be worth it, splice in a same-page A-Z
    index before the list and a "Back to A-Z index" link after it. No-op
    for pages with no <dt> terms. Definition lists with too few terms to
    need an index — e.g. the small 4-entry "Key to Tables ... columns"
    legends elsewhere — still get stable ids but no index, per
    AZ_INDEX_THRESHOLD. Never touches the definitions' own text or order."""
    terms = parse_terms(fragment)
    if not terms:
        return fragment

    dl_spans = find_dl_spans(fragment)
    headings = parse_headings(fragment)
    fragment, assigned = assign_term_ids(fragment, terms)
    new_dl_spans = find_dl_spans(fragment)
    if len(new_dl_spans) != len(dl_spans):
        errors.add(label, "glossary-dl-mismatch",
                   "The number of <dl>...</dl> blocks changed while assigning glossary term ids; "
                   "cannot reliably place the A-Z index.",
                   "Check for <dl> or </dl> text appearing outside an actual definition list.")
        return fragment

    groups = [[] for _ in dl_spans]
    for term, entry in zip(terms, assigned):
        for i, (dstart, dend) in enumerate(dl_spans):
            if dstart <= term.start < dend:
                groups[i].append(entry)
                break

    edits = []
    for i, ((orig_start, _orig_end), (new_start, new_end), group) in enumerate(
            zip(dl_spans, new_dl_spans, groups)):
        if len(group) < AZ_INDEX_THRESHOLD:
            continue
        index_id = "az-index" if i == 0 else f"az-index-{i + 1}"
        # Name each index after the nearest preceding heading (e.g. "3.1
        # Terms", "3.3 Abbreviations") so multiple indexes on one page get
        # distinct, meaningful accessible names, without hardcoding any
        # clause-specific wording here.
        preceding_heading = None
        for h in headings:
            if h.close_end <= orig_start:
                preceding_heading = h
            else:
                break
        aria_label = f"A to Z index for {preceding_heading.text}" if preceding_heading else "A to Z index"
        index_html = build_az_index(group, index_id, aria_label)
        back_link = f'<p class="back-to-az-index"><a href="#{index_id}">Back to A-Z index</a></p>'
        edits.append((new_end, new_end, back_link))
        edits.append((new_start, new_start, index_html))
    edits.sort(key=lambda e: e[0], reverse=True)
    out = fragment
    for start, end, replacement in edits:
        out = out[:start] + replacement + out[end:]
    return out


def render_page(index, page, metadata, summaries, errors, xrefs=None):
    slug = page["slug"]
    is_index = slug == "index"
    fragment_path = CONTENT_DIR / f"{slug}.html"
    if not fragment_path.exists():
        return None  # already reported by validate_sitemap_vs_content

    fragment = fragment_path.read_text(encoding="utf-8")
    fragment = substitute_tokens(fragment, metadata, errors)
    fragment = apply_glossary_terms(fragment, errors, f"content/{slug}.html")
    if slug == "clause-2-references":
        fragment = inject_reference_ids(fragment)
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
    fragment_html = inject_heading_links(fragment, headings)
    if xrefs:
        fragment_html = link_cross_references(fragment_html, slug, xrefs)
    content_html = clause_summary + on_this_page + fragment_html

    html_out = PAGE_TEMPLATE.format(
        title=html.escape(page["title"]),
        doc_label=DOC_LABEL,
        description=html.escape(f'{page["title"]} — {DOC_LABEL} accessible HTML edition (final draft, under approval).'),
        asset_prefix="",
        site_title=build_site_title(""),
        doc_header=build_doc_header(page),
        source_month_year=human_date(metadata["sourcePdfPublicationDate"]) if metadata else "",
        site_nav=build_site_nav(slug, headings),
        content=content_html,
        pager="" if slug in ("index", "search") else build_pager(index),
        source_pdf=SOURCE_PDF_NAME,
        css_version=asset_version(CSS_PATH),
        js_version=asset_version(JS_PATH),
        header_nav=build_header_nav(slug),
        footer_nav=build_footer_nav(slug),
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

    for m in re.finditer(r'<a class="heading-link" href="#([^"]+)"[^>]*>(.*?)</a>', html_out, re.DOTALL):
        frag_id, inner = m.group(1), m.group(2)
        text = strip_tags(inner)
        if len(text) < 2:
            errors.add(label, "heading-link-empty",
                       f'A heading link to "#{frag_id}" has no meaningful text — its accessible name '
                       "is the heading text it wraps, so it must not be empty.",
                       "Check inject_heading_links() wrapped the heading's actual text.")

    if slug == "accessibility-statement":
        if "github.com" not in html_out and "mailto:" not in html_out:
            errors.add(label, "accessibility-statement-no-reporting-route",
                       "The accessibility statement has no reporting link (expected a GitHub issues "
                       "link or a mailto: link).",
                       "Add a real reporting route — see content/accessibility-statement.html.")

    on_this_page_match = re.search(r'<nav class="on-this-page".*?</nav>', html_out, re.DOTALL)
    if on_this_page_match:
        entries = re.findall(r'<a href="#[^"]*">([^<]*)</a>', on_this_page_match.group(0))
        for text in entries:
            text = html.unescape(text).strip()
            if text in UTILITY_HEADING_TEXTS:
                errors.add(label, "on-this-page-utility-heading",
                           f'"On this page" includes "{text}", a website-only utility heading that '
                           "should never appear there.",
                           "Check build_on_this_page() is only fed the fragment's own ETSI headings, "
                           "not clause-summary/on-this-page markup injected before it.")

    # Excludes the "content-meta-list" <dl> used for source/version metadata
    # rows (e.g. on the About page) — those are plain key-value pairs, not
    # glossary/abbreviation definitions, and are never passed through
    # apply_glossary_terms() (they're substituted in afterwards).
    glossary_scan_html = re.sub(r'<dl class="content-meta-list">.*?</dl>', '', html_out, flags=re.DOTALL)
    dt_matches = re.findall(r'<dt([^>]*)>', glossary_scan_html)
    if dt_matches:
        dt_ids = []
        for attrs in dt_matches:
            m = re.search(r'\bid="([^"]*)"', attrs)
            if not m or not m.group(1):
                errors.add(label, "glossary-term-missing-id",
                           "A <dt> definition term was rendered without a stable id.",
                           "Check apply_glossary_terms()/assign_term_ids() ran on this fragment.")
            else:
                dt_ids.append(m.group(1))
        if len(dt_ids) != len(set(dt_ids)):
            errors.add(label, "glossary-term-duplicate-id",
                       "Two or more <dt> definition terms were rendered with the same id.",
                       "Check assign_term_ids()'s collision handling in scripts/build.py.")

    for az_match in re.finditer(r'<nav class="az-index"[^>]*>.*?</nav>', html_out, re.DOTALL):
        az_html = az_match.group(0)
        letter_links = re.findall(r'<a href="#([^"]+)">([A-Z#])<', az_html)
        if not letter_links:
            errors.add(label, "az-index-empty",
                       "An A-Z index was rendered with no letter links.",
                       "Check build_az_index() and the AZ_INDEX_THRESHOLD gate in scripts/build.py.")
        for target_id, letter in letter_links:
            if target_id not in seen:
                errors.add(label, "az-index-broken-link",
                           f'The A-Z index letter "{letter}" links to "#{target_id}", which does not '
                           "exist on this page.",
                           "Check build_az_index() is using ids assigned by assign_term_ids().")
        letters_found = [pair[1] for pair in letter_links]
        if letters_found != sorted(letters_found):
            errors.add(label, "az-index-unsorted",
                       "The A-Z index's letters are not in alphabetical order.",
                       "Check build_az_index() sorts letters before rendering links.")


# ---------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------

SITEMAP = json.loads(SITEMAP_PATH.read_text(encoding="utf-8"))


def main():
    check_only = "--check-only" in sys.argv
    errors = Errors()

    metadata = load_metadata(errors)
    summaries = load_clause_summaries(errors)
    ownership = load_content_ownership()
    validate_content_ownership(ownership, errors)
    validate_sitemap_vs_content(errors)
    validate_etsi_content_integrity(errors)

    if errors:
        errors.report_and_exit()

    xrefs = build_xref_maps(errors)
    if errors:
        errors.report_and_exit()

    rendered = {}
    for i, page in enumerate(SITEMAP):
        html_out = render_page(i, page, metadata, summaries, errors, xrefs)
        if html_out is not None:
            rendered[page["slug"]] = html_out

    if errors:
        errors.report_and_exit()

    all_slugs = set(rendered.keys())
    for slug, html_out in rendered.items():
        validate_rendered_page(slug, html_out, all_slugs, errors)

    # Cross-page anchors: href="other-page.html#id" must point at an id
    # that really exists on that page. (Per-page validation already covers
    # same-page "#id" links; this covers everything the cross-reference
    # linker and hand-authored content produce across pages.)
    ids_by_slug = {s: set(re.findall(r'\sid="([^"]+)"', h)) for s, h in rendered.items()}
    for slug, html_out in rendered.items():
        for href in HREF_RE.findall(html_out):
            m = re.match(r'^([a-z0-9-]+)\.html#(.+)$', href)
            if m and m.group(1) in ids_by_slug and m.group(2) not in ids_by_slug[m.group(1)]:
                errors.add(f"docs/{slug}.html", "broken-cross-page-anchor",
                           f'href="{href}" points at an id that does not exist on {m.group(1)}.html.',
                           "Fix the href, or add the missing id to the target page.")

    if errors:
        errors.report_and_exit()

    missing_governance = content_ownership_notices(ownership)
    if missing_governance:
        print(f"Note: no content ownership/review metadata recorded for: {', '.join(missing_governance)}. "
              "See docs-for-maintainers/content-ownership.md.")

    if check_only:
        print(f"Checked {len(rendered)} pages — no validation errors.")
        return

    DOCS_DIR.mkdir(exist_ok=True)
    for slug, html_out in rendered.items():
        (DOCS_DIR / f"{slug}.html").write_text(html_out, encoding="utf-8")

    index_entries = build_search_index(metadata)
    SEARCH_INDEX_PATH.write_text(
        json.dumps(index_entries, ensure_ascii=False, separators=(",", ":")) + "\n",
        encoding="utf-8")

    print(f"Built {len(rendered)} pages and a {len(index_entries)}-entry search index into {DOCS_DIR}")


if __name__ == "__main__":
    main()
