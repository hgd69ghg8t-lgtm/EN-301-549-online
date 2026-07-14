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
            if field not in CONTENT_OWNERSHIP_FIELDS:
                errors.add(label, "content-ownership-unknown-field",
                           f'Unrecognised field "{field}".',
                           f"Use one of: {', '.join(CONTENT_OWNERSHIP_FIELDS)}.")
                continue
            if value is None:
                continue  # deliberately unknown — not an error
            if field in _CONTENT_OWNERSHIP_DATE_FIELDS:
                if not isinstance(value, str) or value in PLACEHOLDER_DATES:
                    errors.add(label, "content-ownership-date-placeholder",
                               f'"{field}" is "{value}", which looks like a placeholder rather than '
                               "a real date.",
                               f'Set "{field}" to a real YYYY-MM-DD date, or leave it null (not a '
                               "placeholder string) if it isn't known yet.")
                    continue
                try:
                    datetime.date.fromisoformat(value)
                except ValueError:
                    errors.add(label, "content-ownership-date-invalid",
                               f'"{field}" value "{value}" is not a valid ISO date (expected YYYY-MM-DD).',
                               f'Fix "{field}" to a real YYYY-MM-DD date.')
            elif isinstance(value, str) and PLACEHOLDER_RE.search(value):
                errors.add(label, "content-ownership-placeholder",
                           f'"{field}" contains unfilled placeholder text: "{value}".',
                           "Remove the placeholder — leave the field null if the real value isn't "
                           "known yet.")


def content_ownership_notices(ownership):
    """Slugs (among NON_STANDARD_SLUGS) with no governance metadata at all
    — reported as a build-time notice (not an error, and never published
    to the site) so the gap stays visible to maintainers rather than being
    silently forgotten."""
    missing = []
    for slug in sorted(NON_STANDARD_SLUGS):
        entry = ownership.get(slug) or {}
        if not any(entry.get(f) for f in CONTENT_OWNERSHIP_FIELDS):
            missing.append(slug)
    return missing


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
# ETSI wording integrity check (data/etsi-content-hashes.json)
# ---------------------------------------------------------------------
#
# A stored-hash baseline for every clause/annex content/*.html file (every
# sitemap slug except the website-authored NON_STANDARD_SLUGS pages), so an
# accidental or unnoticed edit to reproduced ETSI wording is caught by the
# build rather than discovered later. The baseline is refreshed only by
# deliberately running scripts/update_etsi_hashes.py — never by build.py
# itself — so the check can't be silently defeated by the same change that
# trips it.

ETSI_HASHES_PATH = ROOT / "data" / "etsi-content-hashes.json"


def canonical_etsi_text(raw_html):
    """Text-only canonicalisation for wording-integrity hashing: strips all
    markup and collapses whitespace, so the hash reacts only to the actual
    reproduced words — never to heading levels, ids, classes, attribute
    order, or indentation. Nothing build.py does to content/*.html at
    render time (permalink injection, glossary-term ids, etc.) can trip
    this check, because those transformations never touch content/*.html
    on disk in the first place; they operate on an in-memory copy while
    rendering docs/*.html."""
    return " ".join(strip_tags(raw_html).split())


def etsi_content_hash(raw_html):
    return hashlib.sha256(canonical_etsi_text(raw_html).encode("utf-8")).hexdigest()


def protected_etsi_slugs():
    """Every sitemap slug except the website-authored pages — i.e. every
    clause and annex whose content/*.html is reproduced ETSI wording that
    must never be rewritten, simplified, corrected or paraphrased."""
    return sorted({p["slug"] for p in SITEMAP} - NON_STANDARD_SLUGS)


def load_etsi_hashes():
    if not ETSI_HASHES_PATH.exists():
        return None
    try:
        data = json.loads(ETSI_HASHES_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


def validate_etsi_content_integrity(errors):
    rel = str(ETSI_HASHES_PATH.relative_to(ROOT))
    baseline = load_etsi_hashes()
    if baseline is None:
        errors.add(rel, "etsi-hashes-missing",
                   "data/etsi-content-hashes.json is missing or not valid JSON. Without it, an "
                   "accidental edit to reproduced ETSI wording in content/*.html could go unnoticed.",
                   "Run `python3 scripts/update_etsi_hashes.py` once to generate it from the "
                   "current, known-good content, then commit the result.")
        return

    protected = protected_etsi_slugs()
    for slug in protected:
        fragment_path = CONTENT_DIR / f"{slug}.html"
        if not fragment_path.exists():
            continue  # already reported by validate_sitemap_vs_content
        actual = etsi_content_hash(fragment_path.read_text(encoding="utf-8"))
        expected = baseline.get(slug)
        if expected is None:
            errors.add(rel, "etsi-hash-missing-entry",
                       f'"{slug}" has no recorded wording-integrity hash.',
                       "Run `python3 scripts/update_etsi_hashes.py` to add it — but only after "
                       f"confirming content/{slug}.html's wording is correct and unedited.")
        elif expected != actual:
            errors.add(f"content/{slug}.html", "etsi-wording-changed",
                       f"The reproduced ETSI wording in content/{slug}.html no longer matches the "
                       "recorded wording-integrity baseline — its text content has changed.",
                       "If this is an intentional, verified fix (e.g. correcting a transcription "
                       "error against the source PDF), run `python3 scripts/update_etsi_hashes.py` "
                       "and explain the change in your commit message. If it wasn't intentional, "
                       "revert the wording change.")

    for slug in baseline:
        if slug not in protected:
            errors.add(rel, "etsi-hash-stale-entry",
                       f'"{slug}" has a recorded hash but is not a protected clause/annex page '
                       "(it may be website-authored, renamed, or no longer exist).",
                       "Run `python3 scripts/update_etsi_hashes.py` to regenerate the file, or "
                       "remove the stale entry by hand.")


# ---------------------------------------------------------------------
# Auto-linked cross-references
# ---------------------------------------------------------------------
#
# The reproduced ETSI text constantly refers to other parts of the
# standard — "see clause 5.1.3", "clauses 9, 10 and 11", "Annex ZA",
# "[i.25]" — as dead text, because that's all a PDF can do. At render
# time the build turns those references into links. This is markup only:
# not one character of wording changes (the wording-integrity hash check
# would catch it if it did), and anything the build cannot resolve to a
# real target with certainty is left as plain text — e.g. "Annex I",
# which is an annex of an EU *Directive*, not of this document, resolves
# to nothing and is deliberately not linked.
#
# Only genuine text is touched: anything already inside a link, a
# heading, or a table caption is skipped (the parser tracks ancestors),
# so heading self-links never gain nested links and clause 2's own
# bibliography never links to itself.

XREF_WORD_RE = re.compile(r'\b([Cc]lauses?|[Aa]nnex(?:es)?)(\s+)')
XREF_TOKEN_RE = re.compile(r'[A-Z]{1,2}\.\d+(?:\.\d+)*|\d+(?:\.\d+)*|[A-Z]{1,2}\b')
XREF_CONT_RE = re.compile(r',?\s+(?:and|or|to)\s+|,\s*')
XREF_BRACKET_RE = re.compile(r'\[(i\.\d+|\d+)\]')

# The one deliberate wording-adjacent exception: these tags appear in the
# text as e.g. "[i.25]" and become ids like "ref-i-25" on clause 2's list
# items, so the bracket tokens elsewhere have something to link to.
REF_TAG_LI_RE = re.compile(r'<li><span class="ref-tag">\[(i\.\d+|\d+)\]</span>')


def _ref_id(tag):
    return "ref-" + tag.replace(".", "-")


def inject_reference_ids(fragment):
    """Give each bibliography entry in clause 2 a stable id derived from
    its own [N]/[i.N] tag, so citations elsewhere can deep-link to it."""
    return REF_TAG_LI_RE.sub(
        lambda m: f'<li id="{_ref_id(m.group(1))}"><span class="ref-tag">[{m.group(1)}]</span>',
        fragment)


def build_xref_maps(errors):
    """Site-wide lookup tables for the cross-reference linker, built from
    the same sources everything else uses (sitemap + content fragments):
      headings: "5.1.3" / "C.4" / "ZA.1" -> (slug, anchor id)
      pages:    "9" -> clause page slug (top-level clause numbers are page
                titles, not headings, so they map to whole pages)
      annexes:  "ZA" -> annex page slug ("C" -> the first Annex C page)
      refs:     {"4", "i.25", ...} — bibliography tags that exist
    A clause number appearing on two pages would make links ambiguous, so
    that's a build error, not a guess."""
    headings_map = {}
    pages_map = {}
    annexes_map = {}
    for page in SITEMAP:
        slug = page["slug"]
        if page["group"] == "Clauses":
            number = page["title"].split(" ", 1)[0]
            if number.isdigit():
                pages_map[number] = slug
        m = re.match(r'^Annex\s+([A-Z]{1,2})', page["title"])
        if m and m.group(1) not in annexes_map:
            annexes_map[m.group(1)] = slug
        fragment_path = CONTENT_DIR / f"{slug}.html"
        if not fragment_path.exists():
            continue
        for h in parse_headings(fragment_path.read_text(encoding="utf-8")):
            if not h.number:
                continue
            anchor = h.id or canonical_id(h.number)
            if h.number in headings_map and headings_map[h.number] != (slug, anchor):
                errors.add(f"content/{slug}.html", "xref-ambiguous-number",
                           f'Clause number "{h.number}" appears on both '
                           f"{headings_map[h.number][0]} and {slug}; cross-reference links "
                           "to it would be ambiguous.",
                           "Renumber one of the headings, or fix the duplicated content.")
            headings_map[h.number] = (slug, anchor)
    refs = set()
    clause2 = CONTENT_DIR / "clause-2-references.html"
    if clause2.exists():
        refs = set(REF_TAG_LI_RE.findall(clause2.read_text(encoding="utf-8")))
    return {"headings": headings_map, "pages": pages_map, "annexes": annexes_map, "refs": refs}


def _text_spans(fragment):
    """(start, end) offsets of every raw text node that is safe to link
    inside: not within an existing link, a heading, or a table caption.
    convert_charrefs=False so offsets line up with the source string
    (entities arrive separately and simply split text nodes)."""
    from html.parser import HTMLParser

    excluded = {"a", "h1", "h2", "h3", "h4", "h5", "h6", "caption"}

    class Scanner(HTMLParser):
        def __init__(self):
            super().__init__(convert_charrefs=False)
            self.spans = []
            self.depth = 0
            self._offsets = None

        def _pos(self):
            line, col = self.getpos()
            return self._offsets[line - 1] + col

        def handle_starttag(self, tag, attrs):
            if tag in excluded:
                self.depth += 1

        def handle_endtag(self, tag):
            if tag in excluded and self.depth:
                self.depth -= 1

        def handle_data(self, data):
            if self.depth == 0 and data.strip():
                start = self._pos()
                self.spans.append((start, start + len(data)))

    offsets = [0]
    for line in fragment.splitlines(keepends=True):
        offsets.append(offsets[-1] + len(line))
    scanner = Scanner()
    scanner._offsets = offsets
    scanner.feed(fragment)
    scanner.close()
    return scanner.spans


def _resolve_xref(token, kind, xrefs, current_slug):
    """token -> href, or None when there is no certain target (in which
    case the text is left exactly as it was)."""
    target = None
    if "." in token or token.isdigit():
        target = xrefs["headings"].get(token)
        if target is None and token.isdigit():
            slug = xrefs["pages"].get(token)
            if slug:
                target = (slug, None)
    if target is None and kind == "annex" and token.isalpha():
        slug = xrefs["annexes"].get(token)
        if slug:
            target = (slug, None)
    if target is None:
        return None
    slug, anchor = target
    if slug == current_slug:
        return f"#{anchor}" if anchor else None  # a bare self-page link helps nobody
    return f"{slug}.html#{anchor}" if anchor else f"{slug}.html"


def link_cross_references(fragment, current_slug, xrefs):
    edits = []

    def add_link(abs_start, abs_end, href):
        text = fragment[abs_start:abs_end]
        edits.append((abs_start, abs_end, f'<a class="xref" href="{href}">{text}</a>'))

    for span_start, span_end in _text_spans(fragment):
        text = fragment[span_start:span_end]

        # "clause 5.1.3", "clauses 9, 10 and 11", "Annex ZA", "annexes A and B"
        for m in XREF_WORD_RE.finditer(text):
            kind = "annex" if m.group(1).lower().startswith("annex") else "clause"
            pos = m.end()
            while True:
                tm = XREF_TOKEN_RE.match(text, pos)
                if not tm:
                    break
                href = _resolve_xref(tm.group(0), kind, xrefs, current_slug)
                if href:
                    add_link(span_start + tm.start(), span_start + tm.end(), href)
                pos = tm.end()
                cm = XREF_CONT_RE.match(text, pos)
                if not cm:
                    break
                pos = cm.end()

        # "[4]" / "[i.25]" bibliography citations — everywhere except on
        # the references page itself, where they'd link to themselves.
        if current_slug != "clause-2-references":
            for m in XREF_BRACKET_RE.finditer(text):
                if m.group(1) in xrefs["refs"]:
                    add_link(span_start + m.start(), span_start + m.end(),
                             f"clause-2-references.html#{_ref_id(m.group(1))}")

    # Overlap guard: a token can only be claimed once (first match wins).
    edits.sort(key=lambda e: e[0])
    kept, last_end = [], -1
    for e in edits:
        if e[0] >= last_end:
            kept.append(e)
            last_end = e[1]
    out = fragment
    for start, end, replacement in reversed(kept):
        out = out[:start] + replacement + out[end:]
    return out


# ---------------------------------------------------------------------
# Search index (docs/search-index.json)
# ---------------------------------------------------------------------
#
# A static, build-time search index — no search service, no third-party
# library. One JSON entry per heading section (h2-h4), per glossary term,
# and per page intro: {"u": url, "p": page name, "t": title, "b": body
# text}. docs/assets/js/site.js fetches it on the search page and filters
# it in the browser. Deterministic (same source always produces the same
# bytes), so the repository's reproducible-build guarantee holds.

SEARCH_INDEX_PATH = DOCS_DIR / "search-index.json"
# Long sections (e.g. clause 3's whole "3.1 Terms" block, whose individual
# definitions are indexed separately anyway) are capped so the index stays
# a reasonable download; the cap is generous enough that genuine
# requirement sections are never truncated.
SEARCH_BODY_MAX_CHARS = 4000


def _squash(text):
    return " ".join(strip_tags(text).split())


def build_search_index(metadata):
    """Assembles the index from the same processed fragments the pages are
    rendered from. Runs its own pass with a throwaway error collector —
    any real content problems were already reported during rendering, and
    reporting them twice would just be noise."""
    scratch = Errors()
    entries = []
    for page in SITEMAP:
        slug = page["slug"]
        if slug == "search":
            continue  # the search page itself isn't searchable content
        fragment_path = CONTENT_DIR / f"{slug}.html"
        if not fragment_path.exists():
            continue
        fragment = fragment_path.read_text(encoding="utf-8")
        fragment = substitute_tokens(fragment, metadata, scratch)
        fragment = apply_glossary_terms(fragment, scratch, f"content/{slug}.html")
        headings = parse_headings(fragment)
        page_name = page["shortTitle"]

        intro = _squash(fragment[:headings[0].start] if headings else fragment)
        if intro:
            entries.append({"u": f"{slug}.html", "p": page_name,
                            "t": page["title"], "b": intro[:SEARCH_BODY_MAX_CHARS]})

        for i, h in enumerate(headings):
            if h.level not in (2, 3, 4) or not h.id:
                continue
            end = headings[i + 1].start if i + 1 < len(headings) else len(fragment)
            body = _squash(fragment[h.close_end:end])
            entries.append({"u": f"{slug}.html#{h.id}", "p": page_name,
                            "t": h.text, "b": body[:SEARCH_BODY_MAX_CHARS]})

        # Glossary/abbreviation terms get their own entries, pointing at
        # the stable per-term ids assign_term_ids() created.
        terms = parse_terms(fragment)
        for i, term in enumerate(terms):
            if not term.id:
                continue
            dl_end = fragment.find("</dl>", term.close_end)
            next_start = terms[i + 1].start if i + 1 < len(terms) else len(fragment)
            end = min(x for x in (dl_end, next_start) if x != -1)
            body = _squash(fragment[term.close_end:end])
            entries.append({"u": f"{slug}.html#{term.id}", "p": page_name,
                            "t": term.text, "b": body[:SEARCH_BODY_MAX_CHARS]})
    return entries


# ---------------------------------------------------------------------
# Per-fragment heading validation + heading-link injection
# ---------------------------------------------------------------------

def validate_fragment_headings(slug, raw, headings, errors):
    label = f"content/{slug}.html"

    # Every page's <h1> comes from build_doc_header() (sitemap.json's
    # title) — including the homepage — so no fragment may contain one:
    # two <h1> elements would end up on the same generated page.
    h1s = [h for h in headings if h.level == 1]
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


def inject_heading_links(raw, headings):
    """Wrap every numbered heading's own text in a self-referencing link,
    so the heading itself is the keyboard-focusable permalink — one tab
    stop whose accessible name IS the heading text, rather than a separate
    "#" control after it. Activating it navigates to the heading's anchor
    (address bar now holds the deep link, with no JavaScript needed);
    site.js adds copy-to-clipboard on top. Uses the same byte offsets
    heading_parser.py already computed, so this never touches heading
    text or attributes — only wraps the existing text in an anchor."""
    edits = []
    for h in headings:
        if not h.number:
            continue
        anchor_id = h.id or canonical_id(h.number)
        open_tag = f'<a class="heading-link" href="#{anchor_id}" data-copy-link>'
        edits.append((h.end, h.end, "</a>"))
        edits.append((h.tag_end, h.tag_end, open_tag))
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
    breadcrumb = ['<nav class="breadcrumb" aria-label="Breadcrumb"><ol>']
    if page["slug"] == "index":
        breadcrumb.append('<li aria-current="page">Home</li>')
    else:
        breadcrumb.append('<li><a href="index.html">Home</a></li>')
        if page["group"]:
            breadcrumb.append(f'<li>{html.escape(page["group"])}</li>')
        breadcrumb.append(f'<li aria-current="page">{html.escape(page["shortTitle"])}</li>')
    breadcrumb.append('</ol></nav>')

    return f"""<div class="doc-header">
  <div class="doc-header__inner">
    {"".join(breadcrumb)}
    <div class="doc-header__top">
      <div>
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
    """The header brand is a logo-only link back to the homepage, on every
    page including the homepage itself — a lettermark tile with a
    visually-hidden accessible name carrying the full site title, so
    screen-reader users still hear what the link is and where it goes.
    The page's own <h1> is separate: every page's (including the
    homepage's) comes from build_doc_header()."""
    return (f'<a class="site-header__brand" href="{asset_prefix}index.html">'
            f'<img class="site-logo" src="{asset_prefix}assets/img/logo.svg" alt="" width="40" height="40">'
            '<span class="site-wordmark">Accessible<span class="site-wordmark__accent">Docs</span></span>'
            f'<span class="visually-hidden"> — {DOC_LABEL} Online, home</span></a>')


# The header and footer quick links: the site's own (non-standard) pages,
# reachable from every page without opening the Contents tree — the same
# convention as any ordinary website. Labels match the Contents sidebar
# exactly so the same page is never called two different things.
QUICK_LINKS = [
    ("about", "About this HTML edition"),
    ("accessibility-statement", "Accessibility statement"),
]


def _quick_link(slug, label, current_slug):
    current = ' aria-current="page"' if slug == current_slug else ""
    return f'<a href="{slug}.html"{current}>{html.escape(label)}</a>'


def build_header_nav(current_slug):
    links = "".join(_quick_link(slug, label, current_slug) for slug, label in QUICK_LINKS)
    return f'<nav class="site-header__nav" aria-label="About this website">{links}</nav>'


def build_footer_nav(current_slug):
    items = "".join(
        f"<li>{_quick_link(slug, label, current_slug)}</li>"
        for slug, label in [("index", "Home"), ("search", "Search")] + QUICK_LINKS
    )
    return f'<nav class="site-footer__nav" aria-label="Footer"><ul>{items}</ul></nav>'


PAGE_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title} | {doc_label} Online</title>
<meta name="description" content="{description}">
<link rel="stylesheet" href="{asset_prefix}assets/css/style.css?v={css_version}">
<link rel="icon" href="{asset_prefix}assets/img/favicon.svg" type="image/svg+xml">
<link rel="icon" href="{asset_prefix}assets/img/favicon-32.png" sizes="32x32" type="image/png">
<link rel="apple-touch-icon" href="{asset_prefix}assets/img/apple-touch-icon.png">
</head>
<body>
<a class="skip-link" id="top" href="#main-content">Skip to main content</a>

<header class="site-header">
  <div class="site-header__inner">
    {site_title}
    {header_nav}
    <form class="site-search" role="search" aria-label="Site search" action="search.html">
      <input type="search" name="q" aria-label="Search this standard" autocomplete="off">
      <button type="submit">Search</button>
    </form>
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
    {pager}
  </main>
</div>

<a class="back-to-top" href="#top">&uarr; Back to top</a>

<div id="status-live" class="visually-hidden" role="status" aria-live="polite"></div>

<footer class="site-footer">
  <div class="site-footer__inner">
    {footer_nav}
    <p>Unofficial HTML edition of the {source_month_year} final draft. Standard text &copy; ETSI 2026. <a href="{asset_prefix}about.html">Read how this edition was produced</a>.</p>
  </div>
</footer>
<script src="{asset_prefix}assets/js/site.js?v={js_version}"></script>
</body>
</html>
"""


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


# ---------------------------------------------------------------------
# Glossary term ids + A-Z index (clause 3's <dt> definitions)
# ---------------------------------------------------------------------

def slugify_term(text):
    """'Application Programming Interface (API)' -> 'application-programming-
    interface-api'. Deterministic and stable across builds: the same term
    text always produces the same slug, and the slug depends only on the
    term's own text, never on its position in the list — so adding or
    removing an unrelated term elsewhere in the glossary never changes any
    other term's id or breaks a link to it."""
    slug = re.sub(r'[^a-z0-9]+', '-', text.lower()).strip('-')
    return slug or "term"


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
