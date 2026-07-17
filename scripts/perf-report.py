#!/usr/bin/env python3
"""Measures the delivered size of the generated site under docs/.

Python 3 stdlib only, like every other build-side script here. Reports raw
and gzip-compressed bytes for every generated page and shared asset, plus
the derived figures the performance work is judged by (see
docs/performance-optimisation-spec.md, R-001):

  - total site weight;
  - first-visit weight per page (page HTML gzipped + CSS gzipped + JS
    gzipped + both fonts raw — WOFF2 is already compressed, so gzip on the
    wire neither helps nor is applied by GitHub Pages), reported for the
    worst and median page;
  - the search first-keystroke cost (what the header search box downloads
    the first time someone types in it).

Gzip level 9 approximates what GitHub Pages serves; brotli isn't available
there, so gzip is the honest wire-size metric. Raw sizes are shown for
context. docs/source/*.pdf is excluded from all page-weight figures and
reported separately — it's a deliberate static download, not page weight.

Asset filenames are globbed, not hardcoded, so this keeps working when the
CSS/JS gain content-hashed names (spec R-020).

Usage:
  python3 scripts/perf-report.py            # human-readable report
  python3 scripts/perf-report.py --json F   # also write a snapshot to F
"""
import argparse
import gzip
import json
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DOCS = ROOT / "docs"


def gz(data):
    return len(gzip.compress(data, 9))


def measure(path):
    data = path.read_bytes()
    return {"raw": len(data), "gzip": gz(data)}


def collect():
    """Every measured file, grouped. Sorted paths keep output deterministic."""
    groups = {
        "pages": sorted(DOCS.glob("*.html")),
        "css": sorted((DOCS / "assets" / "css").glob("*.css")),
        "js": sorted((DOCS / "assets" / "js").glob("*.js")),
        "fonts": sorted((DOCS / "assets" / "fonts").glob("*.woff2")),
        "images": sorted((DOCS / "assets" / "img").glob("*")),
        "search": sorted(DOCS.glob("search-index*.json")),
        "pdf": sorted((DOCS / "source").glob("*.pdf")),
    }
    return {
        name: {p.relative_to(DOCS).as_posix(): measure(p) for p in paths}
        for name, paths in groups.items()
    }


def derive(m):
    """The spec's headline figures, computed from the per-file measurements."""
    shared_css_gz = sum(v["gzip"] for v in m["css"].values())
    shared_js_gz = sum(v["gzip"] for v in m["js"].values())
    fonts_raw = sum(v["raw"] for v in m["fonts"].values())
    shared = shared_css_gz + shared_js_gz + fonts_raw

    first_visit = {
        page: v["gzip"] + shared for page, v in m["pages"].items()
    }
    ordered = sorted(first_visit.items(), key=lambda kv: (-kv[1], kv[0]))
    worst_page, worst = ordered[0]
    median = statistics.median(first_visit.values())

    total = sum(v["raw"] for g in ("pages", "css", "js", "fonts", "images",
                                   "search") for v in m[g].values())

    # What the header search box fetches on first use. Today that is the
    # full index; after the spec's task 40 split, the titles file. Whichever
    # exists and is smallest per-purpose is determined by name.
    titles = {k: v for k, v in m["search"].items() if "titles" in k}
    suggestion_source = titles or m["search"]
    first_keystroke = sum(v["gzip"] for v in suggestion_source.values())

    return {
        "shared_css_gzip": shared_css_gz,
        "shared_js_gzip": shared_js_gz,
        "fonts_raw": fonts_raw,
        "first_visit_worst_page": worst_page,
        "first_visit_worst_bytes": worst,
        "first_visit_median_bytes": round(median),
        "search_first_keystroke_gzip": first_keystroke,
        "total_site_raw_excluding_pdf": total,
    }


def kb(n):
    return f"{n / 1024:7.1f} KB"


def print_report(m, d):
    def section(title, entries, top=None):
        print(f"\n{title}")
        rows = sorted(entries.items(), key=lambda kv: (-kv[1]["raw"], kv[0]))
        if top:
            rows = rows[:top]
        for name, v in rows:
            print(f"  {kb(v['raw'])} raw  {kb(v['gzip'])} gzip  {name}")

    section("Shared CSS", m["css"])
    section("Shared JS", m["js"])
    section("Fonts (raw = wire size; WOFF2 is pre-compressed)", m["fonts"])
    section("Search index", m["search"])
    section("Images", m["images"])
    section(f"Pages ({len(m['pages'])} total; ten largest)", m["pages"], top=10)
    section("Source PDF (static download, excluded from page weight)", m["pdf"])

    print("\nDerived (spec R-001)")
    print(f"  {kb(d['shared_css_gzip'])}  CSS gzipped (all pages share it)")
    print(f"  {kb(d['shared_js_gzip'])}  JS gzipped (all pages share it)")
    print(f"  {kb(d['fonts_raw'])}  fonts on the wire")
    print(f"  {kb(d['first_visit_worst_bytes'])}  worst first visit "
          f"({d['first_visit_worst_page']})")
    print(f"  {kb(d['first_visit_median_bytes'])}  median first visit")
    print(f"  {kb(d['search_first_keystroke_gzip'])}  search first-keystroke download (gzipped)")
    print(f"  {kb(d['total_site_raw_excluding_pdf'])}  total site raw, PDF excluded")


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--json", metavar="FILE",
                        help="also write the full measurements as JSON")
    args = parser.parse_args()

    if not DOCS.is_dir():
        print("docs/ not found — run the build first.", file=sys.stderr)
        return 1

    m = collect()
    d = derive(m)
    print_report(m, d)

    if args.json:
        snapshot = {"files": m, "derived": d}
        Path(args.json).write_text(
            json.dumps(snapshot, indent=2, sort_keys=True) + "\n",
            encoding="utf-8")
        print(f"\nSnapshot written to {args.json}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
