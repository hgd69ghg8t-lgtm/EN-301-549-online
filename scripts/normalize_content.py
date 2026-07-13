#!/usr/bin/env python3
"""One-time (and re-runnable) content migration/maintenance tool.

Run this after adding or editing headings in content/*.html:

    python3 scripts/normalize_content.py

It rewrites every content fragment so that:

* the fragment never opens with its own <h1> — the page template supplies
  the single <h1> for every page: the site masthead becomes the homepage's
  <h1>, and every other page's <h1> comes from its title in
  scripts/sitemap.json;
* every numbered heading (a heading whose visible text starts with a
  clause reference such as "9.1.1.1" or "C.8.2.1.1") has an id derived
  purely from that number, e.g. id="9-1-1-1" / id="c-8-2-1-1" — never
  from the heading's descriptive wording, so the id stays stable if the
  wording is later corrected;
* headings that are not numbered (e.g. "Foreword", "Introduction") keep
  whatever id they already had; this script never invents a wording-based
  id for a new heading, since that's exactly the instability objective 5
  is trying to avoid. Give a stable id by hand for any new, unnumbered
  heading that needs one.

This script only touches source-of-truth files under content/. Re-run
scripts/build.py afterwards to regenerate docs/.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from heading_parser import parse_headings, canonical_id  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
CONTENT_DIR = ROOT / "content"

def render_starttag(level, attrs, new_id):
    parts = [f"h{level}"]
    id_written = False
    for k, v in attrs:
        if k == "id":
            parts.append(f'id="{new_id}"')
            id_written = True
        elif v is None:
            parts.append(k)
        else:
            parts.append(f'{k}="{v}"')
    if not id_written:
        parts.append(f'id="{new_id}"')
    return "<" + " ".join(parts) + ">"


def normalize_file(path):
    raw = path.read_text(encoding="utf-8")
    headings = parse_headings(raw)
    if not headings:
        return False

    edits = []  # (start, end, replacement), applied right-to-left

    first = headings[0]
    if first.level == 1:
        remove_end = first.close_end
        # also swallow a single trailing blank line so we don't leave
        # doubled blank lines behind
        if raw[remove_end:remove_end + 2] == "\n\n":
            remove_end += 1
        edits.append((first.start, remove_end, ""))
        headings = headings[1:]

    seen_ids = set()
    for h in headings:
        if h.number:
            new_id = canonical_id(h.number)
            base = new_id
            n = 2
            while new_id in seen_ids:
                new_id = f"{base}-{n}"
                n += 1
            seen_ids.add(new_id)
            if h.id != new_id:
                edits.append((h.start, h.tag_end, render_starttag(h.level, h.attrs, new_id)))
        elif h.id:
            seen_ids.add(h.id)

    if not edits:
        return False

    edits.sort(key=lambda e: e[0], reverse=True)
    out = raw
    for start, end, replacement in edits:
        out = out[:start] + replacement + out[end:]

    if out != raw:
        path.write_text(out, encoding="utf-8")
        return True
    return False


def main():
    changed = []
    for path in sorted(CONTENT_DIR.glob("*.html")):
        if normalize_file(path):
            changed.append(path.name)
    if changed:
        print(f"Normalized {len(changed)} file(s):")
        for name in changed:
            print(f"  {name}")
    else:
        print("No changes needed — all content fragments already normalized.")


if __name__ == "__main__":
    main()
