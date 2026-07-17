import contextlib
import hashlib
import io
import json
import re
import tempfile
import unittest
import urllib.parse
from pathlib import Path

from scripts import build, heading_parser, json_data, normalize_content

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

    FAVICON = Path(__file__).resolve().parent.parent / "assets" / "img" / "favicon.svg"

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

    CSS = (ROOT / "assets" / "css" / "style.css").read_text(encoding="utf-8")
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
        svg = (ROOT / "assets" / "img" / "favicon.svg").read_text(encoding="utf-8")
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


class JsonDataLoaderTests(unittest.TestCase):
    """json_data.load_json_data(): the shared strict loader every
    structured JSON input goes through. A malformed existing file is
    always an error — never silently replaced with a fallback."""

    def load(self, text, *, required=True, expect_type=dict, missing=False):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "file.json"
            if not missing:
                path.write_text(text, encoding="utf-8")
            return json_data.load_json_data(path, "data/file.json",
                                            required=required, expect_type=expect_type)

    def rules(self, *args, **kwargs):
        data, errs = self.load(*args, **kwargs)
        return [rule for _, rule, _, _ in errs]

    def test_valid_file_loads(self):
        data, errs = self.load('{"a": 1}')
        self.assertEqual((data, errs), ({"a": 1}, []))

    def test_required_missing_file_is_an_error(self):
        self.assertEqual(self.rules("", missing=True), ["json-file-missing"])

    def test_optional_missing_file_is_acceptable(self):
        self.assertEqual(self.load("", missing=True, required=False), (None, []))

    def test_malformed_optional_file_is_still_an_error(self):
        self.assertEqual(self.rules('{"a": }', required=False), ["json-syntax-error"])

    def test_syntax_error_reports_line_and_column(self):
        _, errs = self.load('{\n  "a": 1,\n  "b": ,\n}')
        self.assertEqual(errs[0][1], "json-syntax-error")
        self.assertIn("line 3", errs[0][2])
        self.assertIn("column", errs[0][2])

    def test_duplicate_key_is_an_error_naming_the_key(self):
        _, errs = self.load('{"slug": 1, "slug": 2}')
        self.assertEqual(errs[0][1], "json-duplicate-key")
        self.assertIn('"slug"', errs[0][2])

    def test_nested_duplicate_key_is_an_error(self):
        self.assertEqual(self.rules('{"outer": {"k": 1, "k": 2}}'),
                         ["json-duplicate-key"])

    def test_wrong_top_level_type_is_an_error(self):
        _, errs = self.load('[1, 2]', expect_type=dict)
        self.assertEqual(errs[0][1], "json-wrong-top-level-type")
        self.assertIn("object", errs[0][2])
        _, errs = self.load('{"a": 1}', expect_type=list)
        self.assertIn("array", errs[0][2])

    def test_error_ordering_is_deterministic(self):
        first = self.load('{"a": }')
        second = self.load('{"a": }')
        self.assertEqual(first, second)

    def test_malformed_file_never_returns_a_fallback_value(self):
        for text in ('nonsense', '{"a": }', '[1]'):
            data, errs = self.load(text, required=False)
            self.assertIsNone(data)
            self.assertTrue(errs)


class SiteConfigTests(unittest.TestCase):
    """data/site-config.json: the single source of the production base
    URL and project identity, strictly validated."""

    VALID = {
        "siteName": "AccessibleDocs",
        "documentLabel": "ETSI EN 301 549 V4.1.0",
        "baseUrl": "https://example.github.io/project/",
        "repositoryUrl": "https://github.com/example/project",
        "deploymentTarget": "github-pages",
    }

    def rules(self, **overrides):
        config = {**self.VALID, **overrides}
        for field, value in list(overrides.items()):
            if value is None:
                del config[field]
        return [rule for _, rule, _, _ in build.validate_site_config(config)]

    def test_valid_configuration(self):
        self.assertEqual(self.rules(), [])
        self.assertEqual(self.rules(deploymentTarget="cloudflare-pages"), [])

    def test_missing_required_field(self):
        self.assertEqual(self.rules(repositoryUrl=None), ["site-config-missing-field"])

    def test_unknown_field_is_rejected(self):
        self.assertEqual(self.rules(customDomain="example.org"),
                         ["site-config-unknown-field"])

    def test_non_string_value_is_rejected(self):
        self.assertEqual(self.rules(siteName=42), ["site-config-wrong-type"])

    def test_http_base_url_is_rejected(self):
        self.assertEqual(self.rules(baseUrl="http://example.github.io/project/"),
                         ["site-config-url-not-https"])

    def test_base_url_without_hostname_is_rejected(self):
        self.assertEqual(self.rules(baseUrl="https:///project/"),
                         ["site-config-url-invalid-host"])

    def test_base_url_missing_trailing_slash_is_rejected(self):
        self.assertEqual(self.rules(baseUrl="https://example.github.io/project"),
                         ["site-config-base-url-no-trailing-slash"])

    def test_base_url_query_and_fragment_are_rejected(self):
        self.assertEqual(self.rules(baseUrl="https://example.github.io/project/?x=1"),
                         ["site-config-url-has-query-or-fragment"])
        self.assertEqual(self.rules(baseUrl="https://example.github.io/project/#top"),
                         ["site-config-url-has-query-or-fragment"])

    def test_malformed_repository_url_is_rejected(self):
        self.assertEqual(self.rules(repositoryUrl="git@github.com:example/project.git"),
                         ["site-config-url-not-https"])

    def test_unknown_deployment_target_is_rejected(self):
        self.assertEqual(self.rules(deploymentTarget="my-own-server"),
                         ["site-config-unknown-deployment-target"])

    def test_duplicate_keys_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "site-config.json"
            path.write_text('{"siteName": "A", "siteName": "B"}', encoding="utf-8")
            config, errs = build.load_site_config(path, "data/site-config.json")
        self.assertIsNone(config)
        self.assertEqual([rule for _, rule, _, _ in errs], ["json-duplicate-key"])

    def test_committed_configuration_is_the_single_source(self):
        # The build's derived constants must come from the committed file,
        # and loading is deterministic.
        with open(ROOT / "data" / "site-config.json", encoding="utf-8") as f:
            committed = json.load(f)
        self.assertEqual(build.SITE_BASE_URL, committed["baseUrl"])
        self.assertEqual(build.DOC_LABEL, committed["documentLabel"])
        self.assertEqual(build.REPOSITORY_URL, committed["repositoryUrl"])
        first = build.load_site_config()
        second = build.load_site_config()
        self.assertEqual(first, second)
        self.assertEqual(first[0], committed)


class RedirectsValidationTests(unittest.TestCase):
    """validate_redirects(): every active rule in the Cloudflare
    _redirects file is validated; comments and blank lines are legal."""

    def rules(self, text):
        errors = build.Errors()
        build.validate_redirects(text, "deployment/cloudflare/_redirects", errors)
        return [rule for _, rule, _, _ in errors.items]

    def test_comments_blank_lines_and_valid_rules_pass(self):
        text = ("# comment\n"
                "\n"
                "/old-page.html  /about.html  301\n"
                "/other  https://example.org/target  302\n"
                "/default-status  /about.html\n")
        self.assertEqual(self.rules(text), [])

    def test_malformed_rule_fails(self):
        self.assertEqual(self.rules("/only-a-source\n"), ["redirect-malformed"])
        self.assertEqual(self.rules("/a /b 301 extra-field\n"), ["redirect-malformed"])

    def test_source_must_begin_with_slash(self):
        self.assertEqual(self.rules("old.html /new.html 301\n"),
                         ["redirect-source-not-rooted"])

    def test_unsupported_status_fails(self):
        self.assertEqual(self.rules("/a /b 200\n"), ["redirect-status-unsupported"])

    def test_invalid_target_fails(self):
        self.assertEqual(self.rules("/a http://insecure.example/ 301\n"),
                         ["redirect-target-invalid"])
        self.assertEqual(self.rules("/a relative.html 301\n"),
                         ["redirect-target-invalid"])

    def test_duplicate_source_fails(self):
        self.assertEqual(self.rules("/a /b 301\n/a /c 301\n"),
                         ["redirect-duplicate-source"])

    def test_self_redirect_loop_fails(self):
        self.assertEqual(self.rules("/a /a 301\n"), ["redirect-loop"])

    def test_chain_redirect_loop_fails(self):
        self.assertEqual(self.rules("/a /b 301\n/b /a 301\n"), ["redirect-loop"])

    def test_committed_redirects_file_is_valid(self):
        text = (ROOT / "deployment" / "cloudflare" / "_redirects").read_text(encoding="utf-8")
        self.assertEqual(self.rules(text), [])


class AtomicBuildTests(unittest.TestCase):
    """The staged, atomic publish: docs/ is replaced only after the whole
    staged tree validates; failures leave docs/ untouched and remove the
    staging directory; stale files never survive a successful build."""

    PDF_BYTES = b"%PDF-1.4 fake but stable bytes"

    @contextlib.contextmanager
    def fake_site(self):
        """A minimal source tree + patched build-module globals, so
        publish_output() can run end to end against temp directories."""
        saved = {name: getattr(build, name) for name in
                 ("ASSETS_DIR", "SOURCE_DIR", "DEPLOYMENT_DIR", "SOURCE_PDF_PATH", "SITEMAP")}
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            assets = root / "assets"
            for rel in ("css/style.css", "js/site.js", "img/favicon.svg",
                        "img/favicon-32.png", "img/apple-touch-icon.png"):
                path = assets / rel
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("asset: " + rel, encoding="utf-8")
            source = root / "source"
            source.mkdir()
            (source / build.SOURCE_PDF_NAME).write_bytes(self.PDF_BYTES)
            deployment = root / "deployment"
            deployment.mkdir()
            (deployment / "_headers").write_text("/*\n  X-Frame-Options: DENY\n", encoding="utf-8")
            (deployment / "_redirects").write_text("# no active rules\n", encoding="utf-8")
            docs = root / "docs"
            build.ASSETS_DIR = assets
            build.SOURCE_DIR = source
            build.DEPLOYMENT_DIR = deployment
            build.SOURCE_PDF_PATH = source / build.SOURCE_PDF_NAME
            build.SITEMAP = [
                {"slug": "index", "title": "Home", "shortTitle": "Home", "pdfPages": None, "group": ""},
                {"slug": "about", "title": "About", "shortTitle": "About", "pdfPages": None, "group": ""},
                {"slug": "search", "title": "Search", "shortTitle": "Search", "pdfPages": None, "group": ""},
                {"slug": "clause-1-scope", "title": "1 Scope", "shortTitle": "1 Scope",
                 "pdfPages": None, "group": "Clauses"},
            ]
            try:
                yield root, docs
            finally:
                for name, value in saved.items():
                    setattr(build, name, value)

    def rendered_pages(self):
        return {page["slug"]: f'<html><body><h1>{page["title"]}</h1></body></html>'
                for page in build.SITEMAP}

    def publish(self, docs, rendered=None, check_only=False):
        rendered = self.rendered_pages() if rendered is None else rendered
        collected = {slug: build.collect_resources(h) for slug, h in rendered.items()}
        errors = build.Errors()
        return build.publish_output(rendered, collected, [], errors,
                                    check_only=check_only, docs_dir=docs)

    def staging_dirs(self, root):
        return [p for p in root.iterdir() if p.name.startswith(".docs-staging-")]

    def test_successful_staging_and_replacement(self):
        with self.fake_site() as (root, docs):
            self.assertTrue(self.publish(docs))
            self.assertTrue((docs / "index.html").is_file())
            self.assertTrue((docs / "404.html").is_file())
            self.assertTrue((docs / ".nojekyll").is_file())
            self.assertEqual(self.staging_dirs(root), [])

    def test_source_assets_and_deployment_files_are_copied(self):
        with self.fake_site() as (root, docs):
            self.publish(docs)
            self.assertEqual((docs / "assets" / "css" / "style.css").read_text(encoding="utf-8"),
                             "asset: css/style.css")
            self.assertEqual((docs / "_headers").read_bytes(),
                             (build.DEPLOYMENT_DIR / "_headers").read_bytes())
            self.assertEqual((docs / "_redirects").read_bytes(),
                             (build.DEPLOYMENT_DIR / "_redirects").read_bytes())

    def test_pdf_bytes_and_checksum_are_preserved(self):
        with self.fake_site() as (root, docs):
            self.publish(docs)
            published = (docs / "source" / build.SOURCE_PDF_NAME).read_bytes()
            self.assertEqual(published, self.PDF_BYTES)
            self.assertEqual(hashlib.sha256(published).hexdigest(),
                             hashlib.sha256(self.PDF_BYTES).hexdigest())

    def test_stale_files_disappear_after_a_clean_build(self):
        with self.fake_site() as (root, docs):
            (docs / "assets" / "img").mkdir(parents=True)
            (docs / "obsolete-page.html").write_text("old", encoding="utf-8")
            (docs / "assets" / "img" / "obsolete.png").write_text("old", encoding="utf-8")
            self.publish(docs)
            self.assertFalse((docs / "obsolete-page.html").exists())
            self.assertFalse((docs / "assets" / "img" / "obsolete.png").exists())

    def test_every_published_file_originates_from_a_source_or_build_step(self):
        with self.fake_site() as (root, docs):
            self.publish(docs)
            actual = {p.relative_to(docs).as_posix() for p in docs.rglob("*") if p.is_file()}
            expected = (
                {f'{page["slug"]}.html' for page in build.SITEMAP}
                | set(build.GENERATED_EXTRA_FILES) | {".nojekyll"}
                | set(build.DEPLOYMENT_FILES)
                | {f"assets/{rel}" for rel in ("css/style.css", "js/site.js", "img/favicon.svg",
                                               "img/favicon-32.png", "img/apple-touch-icon.png")}
                | {f"source/{build.SOURCE_PDF_NAME}"}
            )
            self.assertEqual(actual, expected)

    def test_failed_build_preserves_docs_and_removes_staging(self):
        with self.fake_site() as (root, docs):
            self.publish(docs)  # a valid published site to protect
            before = {p.relative_to(docs).as_posix(): p.read_bytes()
                      for p in docs.rglob("*") if p.is_file()}
            # sabotage: a malformed redirect rule fails staged validation
            (build.DEPLOYMENT_DIR / "_redirects").write_text("/broken\n", encoding="utf-8")
            with contextlib.redirect_stderr(io.StringIO()) as err:
                with self.assertRaises(SystemExit):
                    self.publish(docs)
            self.assertIn("redirect-malformed", err.getvalue())
            after = {p.relative_to(docs).as_posix(): p.read_bytes()
                     for p in docs.rglob("*") if p.is_file()}
            self.assertEqual(before, after)          # docs/ untouched
            self.assertEqual(self.staging_dirs(root), [])  # no temp left behind

    def test_missing_asset_in_staging_fails_the_build(self):
        with self.fake_site() as (root, docs):
            rendered = self.rendered_pages()
            rendered["index"] = ('<html><body><h1>Home</h1>'
                                 '<img src="assets/img/missing.png" alt=""></body></html>')
            with contextlib.redirect_stderr(io.StringIO()) as err:
                with self.assertRaises(SystemExit):
                    self.publish(docs, rendered=rendered)
            self.assertIn("missing-local-resource", err.getvalue())
            self.assertFalse(docs.exists())  # never created from a failed build
            self.assertEqual(self.staging_dirs(root), [])

    def test_unchanged_source_rebuilds_byte_identically(self):
        with self.fake_site() as (root, docs):
            self.publish(docs)
            first = {p.relative_to(docs).as_posix(): p.read_bytes()
                     for p in docs.rglob("*") if p.is_file()}
            self.publish(docs)
            second = {p.relative_to(docs).as_posix(): p.read_bytes()
                      for p in docs.rglob("*") if p.is_file()}
            self.assertEqual(first, second)

    def test_check_only_validates_without_touching_docs(self):
        with self.fake_site() as (root, docs):
            self.assertFalse(self.publish(docs, check_only=True))
            self.assertFalse(docs.exists())
            self.assertEqual(self.staging_dirs(root), [])


class NotFoundPageTests(unittest.TestCase):
    """The generated docs/404.html: shared design, exactly one <h1>,
    noindex, absolute Home/Search/first-clause links, no automatic
    redirect, and excluded from the sitemap."""

    PAGE = (ROOT / "docs" / "404.html").read_text(encoding="utf-8")
    SITEMAP_XML = (ROOT / "docs" / "sitemap.xml").read_text(encoding="utf-8")

    def test_exactly_one_h1(self):
        h1s = re.findall(r"<h1[^>]*>(.*?)</h1>", self.PAGE, re.S)
        self.assertEqual(len(h1s), 1)
        self.assertIn("Page not found", h1s[0])

    def test_says_the_page_could_not_be_found(self):
        self.assertIn("could not be found", self.PAGE)

    def test_has_noindex_and_no_canonical(self):
        self.assertIn('<meta name="robots" content="noindex">', self.PAGE)
        self.assertNotIn('rel="canonical"', self.PAGE)

    def test_never_redirects_automatically(self):
        self.assertNotIn("http-equiv", self.PAGE.lower().replace("charset", ""))

    def test_home_search_and_first_clause_links_are_absolute(self):
        for target in ("index.html", "search.html", "clause-1-scope.html"):
            self.assertIn(f'href="{build.SITE_BASE_URL}{target}"', self.PAGE)

    def test_no_relative_links_survive(self):
        # served at arbitrary missing paths, so every URL must be absolute
        # or fragment-only.
        for r in build.collect_resources(self.PAGE).resources:
            split = urllib.parse.urlsplit(r.url)
            self.assertTrue(split.scheme or not split.path,
                            f"relative URL on the 404 page: {r.url}")

    def test_excluded_from_sitemap(self):
        self.assertNotIn("404.html", self.SITEMAP_XML)

    def test_uses_shared_site_design(self):
        self.assertIn('class="site-header"', self.PAGE)
        self.assertIn("assets/css/style.css", self.PAGE)


if __name__ == "__main__":
    unittest.main()
