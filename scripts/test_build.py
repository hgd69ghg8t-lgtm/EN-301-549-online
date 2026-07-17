import hashlib
import io
import re
import tempfile
import unittest
from pathlib import Path

from scripts import build, heading_parser, normalize_content

ROOT = Path(__file__).resolve().parent.parent


def css_token(css, block_regex, token):
    """Value of --colour-<token> inside the first block matching block_regex
    in style.css (shallow: reads up to the block's first closing brace at
    the same nesting level it opened)."""
    m = re.search(block_regex + r"\s*\{(.*?)\n\}", css, re.S)
    if not m:
        return None
    decl = re.search(r"--colour-" + token + r"\s*:\s*(#[0-9a-fA-F]{6})\s*;", m.group(1))
    return decl.group(1).lower() if decl else None


class SourcePdfChecksumTests(unittest.TestCase):
    def validate(self, checksum, pdf_bytes=None):
        errors = build.Errors()
        with tempfile.TemporaryDirectory() as directory:
            pdf_path = Path(directory) / "source.pdf"
            if pdf_bytes is not None:
                pdf_path.write_bytes(pdf_bytes)
            build.validate_source_pdf_checksum(
                {"sha256": checksum}, errors, "data/source-metadata.json", pdf_path
            )
        return [rule for _, rule, _, _ in errors.items]

    def test_accepts_matching_checksum_case_insensitively(self):
        pdf = b"test PDF bytes"
        checksum = hashlib.sha256(pdf).hexdigest().upper()
        self.assertEqual(self.validate(checksum, pdf), [])

    def test_rejects_malformed_checksum(self):
        self.assertEqual(
            self.validate("not-a-checksum", b"PDF"),
            ["metadata-sha256-invalid"],
        )

    def test_rejects_missing_pdf(self):
        checksum = hashlib.sha256(b"PDF").hexdigest()
        self.assertEqual(self.validate(checksum), ["source-pdf-missing"])

    def test_rejects_mismatched_pdf(self):
        checksum = hashlib.sha256(b"expected").hexdigest()
        self.assertEqual(
            self.validate(checksum, b"different"),
            ["metadata-sha256-mismatch"],
        )


class FaviconThemeTests(unittest.TestCase):
    """The SVG favicon must genuinely adapt to the browser's colour scheme
    (a previous commit claimed it did while the file carried only fixed
    light colours — this pins the real behaviour)."""

    FAVICON = Path(__file__).resolve().parent.parent / "docs" / "assets" / "img" / "favicon.svg"

    def setUp(self):
        self.svg = self.FAVICON.read_text(encoding="utf-8")

    def test_has_dark_scheme_media_query(self):
        self.assertIn("@media (prefers-color-scheme: dark)", self.svg)

    def test_uses_theme_classes_not_duplicated_shapes(self):
        for cls in (".background", ".document", ".lines"):
            self.assertIn(cls, self.svg)
        # classes are applied to shapes, not just declared in the style block
        for attr in ('class="background"', 'class="document"', 'class="lines"'):
            self.assertIn(attr, self.svg)

    def test_light_and_dark_palettes_are_distinct(self):
        style = self.svg[self.svg.index("<style>"):self.svg.index("</style>")]
        base, dark = style.split("@media (prefers-color-scheme: dark)")
        self.assertIn("#ffffff", base)   # light tile
        self.assertIn("#16191d", dark)   # dark tile matches the site's dark background
        self.assertIn("#dbe6ff", dark)   # light document strokes for dark tabs


class ThemeChromeConstantTests(unittest.TestCase):
    """The browser-chrome colours exist once in build.py; everything else
    must agree with them: the CSS tokens they mirror, the generated
    theme-color metas, and the generated pre-paint script. Each assertion
    compares two independent artefacts, so a change to any single place
    fails here rather than drifting silently."""

    CSS = (ROOT / "docs" / "assets" / "css" / "style.css").read_text(encoding="utf-8")
    PAGE = (ROOT / "docs" / "index.html").read_text(encoding="utf-8")

    def test_constants_match_the_css_tokens_they_mirror(self):
        # chrome-light is by design the brand navy; chrome-dark is the dark
        # theme's page background.
        self.assertEqual(build.THEME_CHROME_LIGHT,
                         css_token(self.CSS, r":root", "brand-navy"))
        self.assertEqual(build.THEME_CHROME_DARK,
                         css_token(self.CSS, r':root\[data-theme="dark"\]', "background"))

    def test_generated_metas_carry_the_constants(self):
        self.assertIn(f'id="theme-colour-light" name="theme-color" '
                      f'media="(prefers-color-scheme: light)" content="{build.THEME_CHROME_LIGHT}"',
                      self.PAGE)
        self.assertIn(f'id="theme-colour-dark" name="theme-color" '
                      f'media="(prefers-color-scheme: dark)" content="{build.THEME_CHROME_DARK}"',
                      self.PAGE)

    def test_pre_paint_script_carries_the_constants(self):
        self.assertIn(f'var LIGHT = "{build.THEME_CHROME_LIGHT}", DARK = "{build.THEME_CHROME_DARK}";',
                      self.PAGE)

    def test_favicon_palette_aligns_with_site_backgrounds(self):
        # The favicon is necessarily a separate SVG asset (a favicon cannot
        # read the page's CSS), so its embedded palette is validated here
        # against the site's: light tile = light page background, dark tile
        # = dark page background (which is also the dark chrome colour).
        svg = (ROOT / "docs" / "assets" / "img" / "favicon.svg").read_text(encoding="utf-8")
        dark_at = svg.index("@media (prefers-color-scheme: dark)")
        light_fill = re.search(r"\.background\s*\{\s*fill:\s*(#[0-9a-fA-F]{6})", svg[:dark_at]).group(1)
        dark_fill = re.search(r"\.background\s*\{\s*fill:\s*(#[0-9a-fA-F]{6})", svg[dark_at:]).group(1)
        self.assertEqual(light_fill.lower(), css_token(self.CSS, r":root", "background"))
        self.assertEqual(dark_fill.lower(), build.THEME_CHROME_DARK)


class PrePaintOrderingTests(unittest.TestCase):
    """Static ordering evidence for the no-flash design: the theme script
    is synchronous and precedes the stylesheet in the generated HTML, so
    an explicit theme is applied before the stylesheet can first paint
    with the wrong tokens. (Real first-paint behaviour is still worth an
    occasional manual look in real browsers.)"""

    PAGE = (ROOT / "docs" / "index.html").read_text(encoding="utf-8")

    def script(self):
        start = self.PAGE.index("Theme apply, deliberately placed before the stylesheet")
        return self.PAGE[start:self.PAGE.index("</script>", start)]

    def test_theme_script_precedes_the_stylesheet(self):
        self.assertLess(self.PAGE.index("Theme apply, deliberately placed before the stylesheet"),
                        self.PAGE.index('<link rel="stylesheet"'))

    def test_theme_metas_precede_the_script(self):
        # the script writes to both metas, so they must already be parsed
        self.assertLess(self.PAGE.index('id="theme-colour-light"'),
                        self.PAGE.index("Theme apply, deliberately placed before the stylesheet"))

    def test_script_applies_the_theme_synchronously(self):
        script = self.script()
        self.assertIn('localStorage.getItem("accessibleDocs.readerPrefs.v1")', script)
        self.assertIn('document.documentElement.setAttribute("data-theme", theme)', script)
        self.assertIn("window.__syncThemeColour(theme || \"auto\")", script)

    def test_script_needs_no_asynchronous_step(self):
        script = self.script()
        for forbidden in ("setTimeout", "setInterval", "requestAnimationFrame",
                          "addEventListener", ".then(", "await ", "Promise"):
            self.assertNotIn(forbidden, script,
                             f"pre-paint script must be synchronous; found {forbidden!r}")


class NormalizeContentTests(unittest.TestCase):
    """scripts/normalize_content.py: the template owns every page's <h1>
    (homepage included), ids come only from clause numbers, duplicates are
    hard errors, and nothing is ever written when validation fails or in
    --check mode."""

    NORMALIZED = ('<p>Intro paragraph.</p>\n\n'
                  '<h2 id="9-1">9.1 First section</h2>\n'
                  '<p>Body.</p>\n')

    def run_tool(self, files, check=False):
        """Run normalize_content.run() over a temp content dir; returns
        (exit_code, {name: bytes after}, stdout, stderr)."""
        with tempfile.TemporaryDirectory() as directory:
            content = Path(directory)
            for name, text in files.items():
                (content / name).write_text(text, encoding="utf-8")
            out, err = io.StringIO(), io.StringIO()
            code = normalize_content.run(content_dir=content, check=check,
                                         out=out, err=err)
            after = {name: (content / name).read_bytes()
                     for name in files}
            return code, after, out.getvalue(), err.getvalue()

    def test_homepage_h1_is_removed(self):
        source = '<h1>Home</h1>\n\n' + self.NORMALIZED
        code, after, _, _ = self.run_tool({"index.html": source})
        self.assertEqual(code, 0)
        self.assertNotIn(b"<h1", after["index.html"])
        self.assertEqual(after["index.html"], self.NORMALIZED.encode())

    def test_non_homepage_h1_is_removed(self):
        source = '<h1>Clause 9</h1>\n\n' + self.NORMALIZED
        code, after, _, _ = self.run_tool({"clause-9-web.html": source})
        self.assertEqual(code, 0)
        self.assertNotIn(b"<h1", after["clause-9-web.html"])

    def test_already_normalized_file_stays_byte_identical(self):
        code, after, _, _ = self.run_tool({"about.html": self.NORMALIZED})
        self.assertEqual(code, 0)
        self.assertEqual(after["about.html"], self.NORMALIZED.encode())

    def test_numbered_heading_id_comes_from_clause_number(self):
        source = '<h2 id="wrong-wording-id">9.1 First section</h2>\n'
        code, after, _, _ = self.run_tool({"a.html": source})
        self.assertEqual(code, 0)
        self.assertEqual(after["a.html"],
                         b'<h2 id="9-1">9.1 First section</h2>\n')

    def test_duplicate_clause_numbers_fail_without_writing(self):
        source = ('<h2 id="9-1">9.1 First heading</h2>\n'
                  '<h2 id="x">9.1 Second heading</h2>\n')
        code, after, _, err = self.run_tool({"a.html": source})
        self.assertNotEqual(code, 0)
        self.assertEqual(after["a.html"], source.encode())
        # actionable error: file, clause number, canonical id, both texts,
        # line numbers, and a fix-it-by-hand instruction
        self.assertIn("content/a.html", err)
        self.assertIn('"9.1"', err)
        self.assertIn('id="9-1"', err)
        self.assertIn("9.1 First heading", err)
        self.assertIn("9.1 Second heading", err)
        self.assertIn("line 1", err)
        self.assertIn("line 2", err)
        self.assertIn("by hand", err)

    def test_duplicate_canonical_id_fails(self):
        source = ('<h2 id="9-1">Foreword</h2>\n'
                  '<h2 id="x">9.1 Numbered heading</h2>\n')
        code, after, _, err = self.run_tool({"a.html": source})
        self.assertNotEqual(code, 0)
        self.assertEqual(after["a.html"], source.encode())
        self.assertIn("collides", err)

    def test_no_suffix_is_ever_invented_for_duplicates(self):
        source = ('<h2 id="9-1">9.1 First heading</h2>\n'
                  '<h2 id="x">9.1 Second heading</h2>\n')
        code, after, _, _ = self.run_tool({"a.html": source})
        self.assertNotEqual(code, 0)
        self.assertNotIn(b'id="9-1-2"', after["a.html"])

    def test_error_in_one_file_blocks_all_writes(self):
        fixable = '<h2 id="wrong">9.2 Fixable heading</h2>\n'
        broken = ('<h2 id="9-1">9.1 A</h2>\n'
                  '<h2 id="x">9.1 B</h2>\n')
        code, after, _, _ = self.run_tool({"a.html": fixable, "b.html": broken})
        self.assertNotEqual(code, 0)
        self.assertEqual(after["a.html"], fixable.encode())
        self.assertEqual(after["b.html"], broken.encode())

    def test_check_mode_reports_but_never_writes(self):
        source = '<h1>Home</h1>\n\n' + self.NORMALIZED
        code, after, out, _ = self.run_tool({"index.html": source}, check=True)
        self.assertEqual(code, 1)
        self.assertEqual(after["index.html"], source.encode())
        self.assertIn("index.html", out)

    def test_check_mode_exits_zero_when_normalized(self):
        code, after, _, _ = self.run_tool({"a.html": self.NORMALIZED}, check=True)
        self.assertEqual(code, 0)
        self.assertEqual(after["a.html"], self.NORMALIZED.encode())

    def test_mid_fragment_h1_is_an_error_not_a_deletion(self):
        source = ('<h2 id="9-1">9.1 A</h2>\n'
                  '<h1>Stray heading</h1>\n')
        code, after, _, err = self.run_tool({"a.html": source})
        self.assertNotEqual(code, 0)
        self.assertEqual(after["a.html"], source.encode())
        self.assertIn("opening heading", err)

    def test_output_is_deterministic_and_idempotent(self):
        source = '<h1>T</h1>\n\n<h2 id="w">9.1 Section</h2>\n'
        code1, after1, _, _ = self.run_tool({"a.html": source})
        code2, after2, _, _ = self.run_tool({"a.html": source})
        self.assertEqual((code1, after1), (code2, after2))
        # a second pass over the normalised result changes nothing
        normalised = after1["a.html"].decode()
        code3, after3, out, _ = self.run_tool({"a.html": normalised})
        self.assertEqual(code3, 0)
        self.assertEqual(after3["a.html"], after1["a.html"])
        self.assertIn("No changes needed", out)


class ResourceCollectorTests(unittest.TestCase):
    """collect_resources(): the HTMLParser-based replacement for the old
    href="..." regex — it must see single-quoted/unquoted attributes,
    src, and every srcset candidate."""

    def urls(self, html_text):
        return [r.url for r in build.collect_resources(html_text).resources]

    def test_double_and_single_quoted_and_unquoted_href(self):
        html_text = ('<a href="a.html">a</a>'
                     "<a href='b.html'>b</a>"
                     "<a href=c.html>c</a>")
        self.assertEqual(self.urls(html_text), ["a.html", "b.html", "c.html"])

    def test_src_and_srcset_candidates(self):
        html_text = ('<img src="img/a.png" alt="" '
                     'srcset="img/a.png 1x, img/b.png 2x, img/c.png 400w">')
        self.assertEqual(self.urls(html_text),
                         ["img/a.png", "img/a.png", "img/b.png", "img/c.png"])

    def test_parse_srcset_extracts_urls_and_ignores_descriptors(self):
        self.assertEqual(build.parse_srcset("a.png 1x, b.png 2x, c.png 400w"),
                         ["a.png", "b.png", "c.png"])
        self.assertEqual(build.parse_srcset("solo.png"), ["solo.png"])

    def test_ids_are_collected_with_line_numbers(self):
        page = build.collect_resources('<p id="one">x</p>\n<p id="two">y</p>')
        self.assertEqual([(i, line) for i, line in page.ids],
                         [("one", 1), ("two", 2)])

    def test_entity_encoded_href_is_decoded(self):
        # HTMLParser decodes entities, so the collected URL is the one a
        # browser would actually request.
        self.assertEqual(self.urls('<a href="a.html?x=1&amp;y=2">a</a>'),
                         ["a.html?x=1&y=2"])


class ResourceValidationTests(unittest.TestCase):
    """validate_site_resources(): existence, docs/-tree containment, and
    fragment checks for every internal href/src/srcset reference."""

    ASSETS = ("assets/css/style.css", "assets/js/site.js",
              "assets/img/a.png", "source/standard.pdf")

    def validate(self, pages):
        """pages: {slug: fragment-of-body-html}. Returns errors.items."""
        errors = build.Errors()
        with tempfile.TemporaryDirectory() as directory:
            docs = Path(directory)
            for rel in self.ASSETS:
                path = docs / rel
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("x", encoding="utf-8")
            collected = {slug: build.collect_resources(html_text)
                         for slug, html_text in pages.items()}
            build.validate_site_resources(pages, collected, errors, docs_dir=docs)
        return errors.items

    def rules(self, pages):
        return [rule for _, rule, _, _ in self.validate(pages)]

    def test_valid_site_produces_no_errors(self):
        pages = {
            "index": ('<link href="assets/css/style.css?v=abc123">'
                      '<script src="assets/js/site.js"></script>'
                      '<img src="assets/img/a.png" alt="">'
                      '<a href="about.html">about</a>'
                      '<a href="./about.html">about</a>'
                      '<a href="assets/../about.html">about</a>'
                      '<a href="source/standard.pdf">pdf</a>'
                      '<a href="#here">same page</a>'
                      '<a href="about.html#a-sec">cross page</a>'
                      '<a href="about.html?q=1#a-sec">query then fragment</a>'
                      '<a href="about.html#a%2Dsec">encoded fragment</a>'
                      '<a href="https://example.org/">ext</a>'
                      '<a href="http://example.org/">ext</a>'
                      '<a href="mailto:x@example.org">mail</a>'
                      '<a href="tel:+6400000000">tel</a>'
                      '<img src="data:image/gif;base64,R0lGOD" alt="">'
                      '<p id="here">x</p>'),
            "about": '<h2 id="a-sec">Section</h2>',
        }
        self.assertEqual(self.validate(pages), [])

    def test_missing_same_page_fragment(self):
        self.assertEqual(self.rules({"index": '<a href="#nope">x</a>'}),
                         ["missing-fragment-target"])

    def test_missing_cross_page_fragment(self):
        pages = {"index": '<a href="about.html#nope">x</a>',
                 "about": '<h2 id="a-sec">Section</h2>'}
        items = self.validate(pages)
        self.assertEqual([rule for _, rule, _, _ in items],
                         ["missing-fragment-target"])
        # actionable: source page, original value, target page, missing id
        _, _, message, fix = items[0]
        self.assertIn('href="about.html#nope"', message)
        self.assertIn("about.html", message)
        self.assertIn('"nope"', message)
        self.assertIn('id="nope"', fix)

    def test_missing_local_file(self):
        items = self.validate({"index": '<a href="missing.pdf">x</a>'})
        self.assertEqual([rule for _, rule, _, _ in items],
                         ["missing-local-resource"])
        self.assertIn('"missing.pdf"', items[0][2])

    def test_missing_srcset_candidate_is_reported_individually(self):
        pages = {"index": ('<img src="assets/img/a.png" alt="" '
                           'srcset="assets/img/a.png 1x, assets/img/missing.png 2x">')}
        items = self.validate(pages)
        self.assertEqual([rule for _, rule, _, _ in items],
                         ["missing-local-resource"])
        self.assertIn("assets/img/missing.png", items[0][2])

    def test_path_traversal_is_rejected(self):
        self.assertEqual(self.rules({"index": '<a href="../outside.html">x</a>'}),
                         ["invalid-local-url"])

    def test_root_absolute_path_is_rejected(self):
        self.assertEqual(self.rules({"index": '<a href="/index.html">x</a>'}),
                         ["invalid-local-url"])

    def test_javascript_url_is_rejected(self):
        self.assertEqual(self.rules({"index": '''<a href="javascript:alert('x')">x</a>'''}),
                         ["javascript-url"])

    def test_empty_and_fragment_only_urls_are_tolerated(self):
        self.assertEqual(self.validate({"index": '<a href="">x</a><a href="#">y</a>'}), [])

    def test_stale_top_level_html_on_disk_does_not_satisfy_a_link(self):
        errors = build.Errors()
        with tempfile.TemporaryDirectory() as directory:
            docs = Path(directory)
            (docs / "stale.html").write_text("old page", encoding="utf-8")
            pages = {"index": '<a href="stale.html">x</a>'}
            collected = {slug: build.collect_resources(h) for slug, h in pages.items()}
            build.validate_site_resources(pages, collected, errors, docs_dir=docs)
        self.assertEqual([rule for _, rule, _, _ in errors.items],
                         ["missing-local-resource"])

    def test_error_ordering_is_deterministic_and_page_sorted(self):
        pages = {"zebra": '<a href="gone-z.html">x</a><a href="#no-z">y</a>',
                 "alpha": '<a href="gone-a.html">x</a>'}
        first = self.validate(pages)
        second = self.validate(pages)
        self.assertEqual(first, second)
        self.assertEqual([label for label, _, _, _ in first],
                         ["docs/alpha.html", "docs/zebra.html", "docs/zebra.html"])


class AttributeEscapingTests(unittest.TestCase):
    """escape_attr() and the two start-tag reconstructors: parsed attribute
    values (already entity-decoded by HTMLParser) must be re-escaped when
    written back into HTML, exactly once."""

    def test_escape_attr_covers_the_dangerous_characters(self):
        self.assertEqual(heading_parser.escape_attr('A & B'), 'A &amp; B')
        self.assertEqual(heading_parser.escape_attr('say "hi"'), 'say &quot;hi&quot;')
        self.assertEqual(heading_parser.escape_attr("it's"), "it&#x27;s")
        self.assertEqual(heading_parser.escape_attr('a < b > c'), 'a &lt; b &gt; c')
        self.assertEqual(heading_parser.escape_attr('café — ✓'), 'café — ✓')

    def test_dt_reconstruction_escapes_values_and_keeps_order(self):
        tag = build.render_dt_starttag(
            [("data-label", 'A & B'), ("class", "term")], "def-a-b")
        self.assertEqual(tag, '<dt data-label="A &amp; B" class="term" '
                              'id="def-a-b" tabindex="-1">')

    def test_dt_reconstruction_preserves_existing_id_position_and_tabindex(self):
        tag = build.render_dt_starttag(
            [("id", "old"), ("tabindex", "0"), ("hidden", None)], "def-new")
        self.assertEqual(tag, '<dt id="def-new" tabindex="-1" hidden>')

    def test_heading_reconstruction_escapes_values(self):
        tag = normalize_content.render_starttag(
            2, [("id", "old"), ("data-label", 'A "quoted" <value> & more')], "9-1")
        self.assertEqual(tag, '<h2 id="9-1" data-label="A &quot;quoted&quot; '
                              '&lt;value&gt; &amp; more">')

    def test_round_trip_never_double_escapes(self):
        # Source markup carries &amp;; HTMLParser decodes it to & when
        # parsing; re-serialising must produce &amp; again — not &amp;amp;.
        terms = heading_parser.parse_terms(
            '<dl><dt data-label="A &amp; B">term</dt><dd>d</dd></dl>')
        tag = build.render_dt_starttag(terms[0].attrs, "def-term")
        self.assertIn('data-label="A &amp; B"', tag)
        self.assertNotIn("&amp;amp;", tag)

        headings = heading_parser.parse_headings(
            '<h2 id="x" data-note="1 &lt; 2 &amp; 3">9.1 Heading</h2>')
        tag = normalize_content.render_starttag(2, headings[0].attrs, "9-1")
        self.assertEqual(tag, '<h2 id="9-1" data-note="1 &lt; 2 &amp; 3">')

    def test_unicode_and_boolean_attributes_survive(self):
        tag = build.render_dt_starttag(
            [("data-label", "café ✓"), ("hidden", None)], "def-cafe")
        self.assertEqual(tag, '<dt data-label="café ✓" hidden '
                              'id="def-cafe" tabindex="-1">')


if __name__ == "__main__":
    unittest.main()
