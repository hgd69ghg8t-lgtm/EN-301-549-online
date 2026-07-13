"""Shared HTML heading parser used by scripts/build.py and scripts/normalize_content.py.

Uses Python's standard-library html.parser.HTMLParser instead of a regular
expression, so heading extraction is correct regardless of attribute order,
nested inline elements (e.g. <abbr>, <sup>), escaped characters (entities
are decoded automatically by HTMLParser with convert_charrefs=True), or
extra whitespace inside the heading. No third-party dependency is added:
html.parser ships with every CPython install.
"""
from html.parser import HTMLParser

HEADING_TAGS = {"h1", "h2", "h3", "h4", "h5", "h6"}

# A numbered clause reference at the start of heading text, e.g. "9.1.1.1",
# "C.8.2.1.1", "ZA.1", "A.2.0". Optional 1-3 letter prefix (annex letter),
# then one or more dot-separated integers.
import re
NUMBER_RE = re.compile(r'^([A-Za-z]{1,3}\.)?(\d+(?:\.\d+)*)(?=[\s:]|$)')


class Heading:
    __slots__ = ("level", "id", "attrs", "text", "number", "start", "tag_end", "end", "close_end")

    def __init__(self, level, id_, attrs, text, number, start, tag_end, end):
        self.level = level
        self.id = id_
        self.attrs = attrs        # full attribute list, in source order
        self.text = text
        self.number = number
        self.start = start        # offset of '<' in the opening tag
        self.tag_end = tag_end    # offset just after '>' of the opening tag
        self.end = end            # offset of '<' in the closing tag
        self.close_end = end + len(f"</h{level}>")  # offset just after the closing tag

    def __repr__(self):
        return f"Heading(h{self.level} id={self.id!r} text={self.text!r})"


def clause_number(text):
    """Extract the leading numbered clause reference from heading text, if any."""
    m = NUMBER_RE.match(text.strip())
    if not m:
        return None
    prefix = (m.group(1) or "").rstrip(".")
    digits = m.group(2)
    return f"{prefix}.{digits}" if prefix else digits


def canonical_id(number):
    """Turn a clause number like 'C.8.2.1.1' or '9.1.1.1' into a stable id
    like 'c-8-2-1-1' or '9-1-1-1'. IDs are derived purely from the numbered
    reference, never from the heading's descriptive wording, so a later
    wording edit can never break a direct link to this heading."""
    return number.lower().replace(".", "-")


def _line_offsets(text):
    offsets = [0]
    for line in text.splitlines(keepends=True):
        offsets.append(offsets[-1] + len(line))
    return offsets


class _HeadingScanner(HTMLParser):
    def __init__(self, raw):
        super().__init__(convert_charrefs=True)
        self.raw = raw
        self._line_offsets = _line_offsets(raw)
        self.headings = []
        self._stack = []

    def _offset(self):
        line, col = self.getpos()
        return self._line_offsets[line - 1] + col

    def handle_starttag(self, tag, attrs):
        if tag not in HEADING_TAGS:
            return
        attrs_d = dict(attrs)
        start = self._offset()
        tag_text = self.get_starttag_text() or ""
        self._stack.append({
            "level": int(tag[1]),
            "id": attrs_d.get("id"),
            "attrs": list(attrs),
            "text": [],
            "start": start,
            "tag_end": start + len(tag_text),
        })

    def handle_startendtag(self, tag, attrs):
        # Headings are never self-closed in this content, but handle it
        # defensively rather than silently mis-parsing.
        self.handle_starttag(tag, attrs)
        if tag in HEADING_TAGS:
            self.handle_endtag(tag)

    def handle_data(self, data):
        if self._stack:
            self._stack[-1]["text"].append(data)

    def handle_endtag(self, tag):
        if tag not in HEADING_TAGS or not self._stack:
            return
        entry = self._stack.pop()
        end = self._offset()
        text = " ".join("".join(entry["text"]).split())
        number = clause_number(text)
        self.headings.append(Heading(
            entry["level"], entry["id"], entry["attrs"], text, number,
            entry["start"], entry["tag_end"], end,
        ))


def parse_headings(fragment_html):
    """Return every h1-h6 heading in document order, with byte offsets into
    the original string so callers can do precise text-surgery (e.g.
    inserting a permalink control just before the closing tag)."""
    scanner = _HeadingScanner(fragment_html)
    scanner.feed(fragment_html)
    scanner.close()
    return scanner.headings
