#!/usr/bin/env python3
"""Re-runnable content normalisation/maintenance tool.

Run this after adding or editing headings in content/*.html:

    python3 scripts/normalize_content.py            # rewrite files
    python3 scripts/normalize_content.py --check    # report only, write nothing

It normalises every content fragment so that:

* the fragment no longer opens with its own <h1> — the page template owns
  the single <h1> for every page, including the homepage (build.py's
  h1-in-fragment rule rejects any fragment <h1>);
* every numbered heading (a heading whose visible text starts with a
  clause reference such as "9.1.1.1" or "C.8.2.1.1") has an id derived
  purely from that number, e.g. id="9-1-1-1" / id="c-8-2-1-1" — never
  from the heading's descriptive wording, so the id stays stable if the
  wording is later corrected;
* headings that are not numbered (e.g. "Foreword", "Introduction") keep
  whatever id they already had; this script never invents a wording-based
  id for a new heading, since that's exactly the instability the
  number-derived rule avoids. Give a stable id by hand for any new,
  unnumbered heading that needs one.

Duplicated clause numbers (or otherwise colliding canonical ids) are an
error, never something to paper over with an invented -2/-3 suffix: the
tool reports both headings and stops without writing anything, because
only a human can decide which source numbering is correct. The whole
input set is validated before any file is rewritten, so a single bad
file never leaves the rest half-updated.

Exit status: 0 when every fragment is already normalised and valid;
non-zero when validation fails or (in --check mode) changes are needed.

This script only touches source-of-truth files under content/. Re-run
scripts/build.py afterwards to regenerate docs/.
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from heading_parser import parse_headings, canonical_id, escape_attr  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
CONTENT_DIR = ROOT / "content"


def _line_of(raw, offset):
    return raw.count("\n", 0, offset) + 1


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
            parts.append(f'{k}="{escape_attr(v)}"')
    if not id_written:
        parts.append(f'id="{new_id}"')
    return "<" + " ".join(parts) + ">"


def normalize_text(label, raw):
    """Compute the normalised form of one fragment. Pure function, no I/O.

    Returns (normalised_text, errors): errors is a list of message strings;
    when it is non-empty, normalised_text is None and nothing may be
    written for this file (callers must also withhold every *other* file's
    write — see run()).
    """
    headings = parse_headings(raw)
    errors = []
    edits = []  # (start, end, replacement), applied right-to-left

    if headings and headings[0].level == 1:
        first = headings[0]
        remove_end = first.close_end
        if first.start == 0:
            # the fragment must not begin with blank lines once its
            # opening <h1> is gone
            while raw[remove_end:remove_end + 1] == "\n":
                remove_end += 1
        elif raw[remove_end:remove_end + 2] == "\n\n":
            # swallow a single trailing blank line so we don't leave
            # doubled blank lines behind
            remove_end += 1
        edits.append((first.start, remove_end, ""))
        headings = headings[1:]

    # An <h1> that is *not* the fragment's opening heading is ambiguous
    # source data — it may be mis-levelled real content, so deleting it
    # could silently drop reproduced wording. Report it instead.
    for h in headings:
        if h.level == 1:
            errors.append(
                f"{label}: <h1> at line {_line_of(raw, h.start)} "
                f'("{h.text}") is not the fragment\'s opening heading.\n'
                "  This tool only removes a leading <h1> (the page template "
                "supplies every page's <h1>).\n"
                "  Fix the heading level (or remove the element) by hand — "
                "an <h1> mid-fragment may be real content at the wrong level."
            )

    # id -> (clause number or None, heading text, line)
    seen = {}
    for h in headings:
        if h.level == 1:
            continue  # already reported above
        if h.number:
            new_id = canonical_id(h.number)
            if new_id in seen:
                first_number, first_text, first_line = seen[new_id]
                if first_number is not None:
                    what = f'Clause number "{h.number}" is duplicated'
                else:
                    what = (f'Canonical id "{new_id}" (from clause number '
                            f'"{h.number}") collides with an existing id')
                errors.append(
                    f"{label}: {what} — both headings would get id=\"{new_id}\".\n"
                    f'  first: line {first_line}: "{first_text}"\n'
                    f'  again: line {_line_of(raw, h.start)}: "{h.text}"\n'
                    "  Correct the duplicated source numbering by hand — this "
                    "tool will not choose which heading is right."
                )
                continue
            seen[new_id] = (h.number, h.text, _line_of(raw, h.start))
            if h.id != new_id:
                edits.append((h.start, h.tag_end,
                              render_starttag(h.level, h.attrs, new_id)))
        elif h.id:
            if h.id in seen:
                first_number, first_text, first_line = seen[h.id]
                errors.append(
                    f'{label}: id "{h.id}" is used by more than one heading.\n'
                    f'  first: line {first_line}: "{first_text}"\n'
                    f'  again: line {_line_of(raw, h.start)}: "{h.text}"\n'
                    "  Give one of the two headings a different, unique id "
                    "by hand — this tool will not choose."
                )
                continue
            seen[h.id] = (None, h.text, _line_of(raw, h.start))

    if errors:
        return None, errors
    if not edits:
        return raw, []

    edits.sort(key=lambda e: e[0], reverse=True)
    out = raw
    for start, end, replacement in edits:
        out = out[:start] + replacement + out[end:]
    return out, []


def run(content_dir=CONTENT_DIR, check=False, out=sys.stdout, err=sys.stderr):
    """Normalise every content fragment. Returns the process exit code.

    The complete input set is validated first; if any file has an error,
    nothing at all is written (not even the valid files), so the content
    tree can never be left partially rewritten. In --check mode nothing is
    ever written: exit 0 means everything is already normalised and valid,
    non-zero means changes are required or errors exist.
    """
    changes = []  # (path, normalised_text)
    all_errors = []
    for path in sorted(content_dir.glob("*.html")):
        raw = path.read_text(encoding="utf-8")
        normalised, errors = normalize_text(f"content/{path.name}", raw)
        if errors:
            all_errors.extend(errors)
        elif normalised != raw:
            changes.append((path, normalised))

    if all_errors:
        err.write(f"{len(all_errors)} validation error(s):\n\n")
        for message in all_errors:
            err.write(message + "\n\n")
        err.write("No files were changed.\n")
        return 1

    if not changes:
        out.write("No changes needed — all content fragments already normalized.\n")
        return 0

    if check:
        out.write(f"{len(changes)} file(s) need normalising:\n")
        for path, _ in changes:
            out.write(f"  {path.name}\n")
        out.write("Run `python3 scripts/normalize_content.py` to rewrite them.\n")
        return 1

    for path, normalised in changes:
        path.write_text(normalised, encoding="utf-8")
    out.write(f"Normalized {len(changes)} file(s):\n")
    for path, _ in changes:
        out.write(f"  {path.name}\n")
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Normalise content/*.html headings (see module docstring).")
    parser.add_argument("--check", action="store_true",
                        help="report required changes without writing any file; "
                             "exit 0 only if everything is already normalised and valid")
    args = parser.parse_args(argv)
    return run(check=args.check)


if __name__ == "__main__":
    sys.exit(main())
