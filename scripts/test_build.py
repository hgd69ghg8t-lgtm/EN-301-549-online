import contextlib
import hashlib
import io
import json
import re
import tempfile
import unittest
import urllib.parse
from pathlib import Path

from scripts import build, heading_parser, json_data, minify, normalize_content

ROOT = Path(__file__).resolve().parent.parent


def real_manifest():
    """The build's fingerprinted-asset manifest for the committed source
    (deterministic), for tests that render a page needing asset URLs."""
    manifest, _files = build.compute_assets(build.Errors())
    return manifest


def css_token(css, block_regex, token):
    """Value of --colour-<token> inside the first block matching block_regex
    in style.css (shallow: reads up to the block's first closing brace at
    the same nesting level it opened)."""
    m = re.search(block_regex + r"\s*\{(.*?)\n\}", css, re.S)
    if not m:
        return None
    decl = re.search(r"--colour-" + token + r"\s*:\s*(#[0-9a-fA-F]{6})\s*;", m.group(1))
    return decl.group(1).lower() if decl else None


class MinifyTests(unittest.TestCase):
    """scripts/minify.py: deterministic, semantics-preserving minifiers.
    Strings, template literals, regex literals and url() are never
    touched; comments (except /*!) are dropped; whitespace is only ever
    collapsed to a single separator (newline-preserving for JS)."""

    def test_js_drops_comments_but_keeps_bang_licence(self):
        out = minify.minify_js("/*! keep me */\n// gone\nvar x = 1; /* gone */\n")
        self.assertIn("/*! keep me */", out)
        self.assertNotIn("// gone", out)
        self.assertNotIn("/* gone */", out)
        self.assertIn("var x = 1;", out)

    def test_js_preserves_string_and_regex_contents(self):
        src = 'var s = "a  b   c";\nvar r = /a  b/g;\nvar t = x / y;\n'
        out = minify.minify_js(src)
        self.assertIn('"a  b   c"', out)   # spaces inside string kept
        self.assertIn("/a  b/g", out)      # spaces inside regex kept
        self.assertIn("x / y", out.replace("\n", " "))  # division still valid

    def test_js_is_deterministic_and_idempotent(self):
        src = (JS_DIR := ROOT / "assets" / "js") and (JS_DIR / "core.js").read_text(encoding="utf-8")
        once = minify.minify_js(src)
        self.assertEqual(once, minify.minify_js(src))
        # re-minifying already-minified output is stable
        self.assertEqual(once, minify.minify_js(once))

    def test_js_newlines_preserved_for_asi_safety(self):
        # Two statements without semicolons must not be joined onto one
        # line (that could change meaning via ASI).
        out = minify.minify_js("var a = 1\nvar b = 2\n")
        self.assertIn("\n", out.strip())

    def test_css_collapses_whitespace_and_drops_comments(self):
        out = minify.minify_css("/* c */\n.a {\n  color:  red;\n}\n")
        self.assertNotIn("/* c */", out)
        self.assertIn(".a{", out)
        self.assertNotIn("  ", out)

    def test_css_keeps_bang_licence_and_string_and_url_contents(self):
        out = minify.minify_css('/*! keep */\n.a{content:"x  y";background:url(../a b.png)}\n')
        self.assertIn("/*! keep */", out)
        self.assertIn('"x  y"', out)
        self.assertIn("url(../a b.png)", out)

    def test_committed_modules_stay_valid_after_minification(self):
        # Every JS bundle minifies to output whose braces/parens balance
        # (a cheap structural smoke test; the browser suites run the real
        # minified bundles end to end).
        for modules in build.JS_BUNDLES.values():
            src = "\n".join((ROOT / "assets" / "js" / m).read_text(encoding="utf-8")
                            for m in modules)
            out = minify.minify_js(src)
            self.assertEqual(out.count("{"), out.count("}"))
            self.assertEqual(out.count("("), out.count(")"))


class AssetPipelineTests(unittest.TestCase):
    """compute_assets(): minified, content-fingerprinted CSS/JS bundles
    with a deterministic manifest; the split into conditional bundles."""

    def manifest_files(self):
        return build.compute_assets(build.Errors())

    def test_manifest_has_style_and_all_js_bundles(self):
        manifest, files = self.manifest_files()
        self.assertEqual(set(manifest), {"style"} | set(build.JS_BUNDLES))
        for name, rel in manifest.items():
            self.assertIn(rel, files)

    def test_fingerprinted_names_and_no_query_busters(self):
        manifest, _ = self.manifest_files()
        self.assertRegex(manifest["style"], r"^assets/css/style\.[0-9a-f]{8}\.css$")
        self.assertRegex(manifest["main"], r"^assets/js/main\.[0-9a-f]{8}\.js$")
        for rel in manifest.values():
            self.assertNotIn("?", rel)  # fingerprint replaces ?v= busting

    def test_hash_is_deterministic_for_unchanged_content(self):
        first, _ = self.manifest_files()
        second, _ = self.manifest_files()
        self.assertEqual(first, second)

    def test_hash_changes_when_content_changes(self):
        errors = build.Errors()
        data = b"body{color:red}\n"
        rel1 = build._fingerprinted_path("css", "style", "css", data)
        rel2 = build._fingerprinted_path("css", "style", "css", data + b"/*x*/")
        self.assertNotEqual(rel1, rel2)
        # identical bytes -> identical name
        self.assertEqual(rel1, build._fingerprinted_path("css", "style", "css", data))

    def test_missing_module_is_a_build_error(self):
        saved = build.JS_BUNDLES
        build.JS_BUNDLES = dict(saved, main=saved["main"] + ["does-not-exist.js"])
        try:
            _, _ = build.compute_assets(errors := build.Errors())
        finally:
            build.JS_BUNDLES = saved
        self.assertIn("asset-source-missing", [rule for _, rule, _, _ in errors.items])

    def test_committed_style_is_minified_in_docs(self):
        manifest, _ = self.manifest_files()
        published = (ROOT / "docs" / manifest["style"]).read_bytes()
        source = (ROOT / "assets" / "css" / "style.css").read_bytes()
        self.assertLess(len(published), len(source))  # minified
        self.assertNotIn(b"\n\n", published)


class ConditionalScriptTests(unittest.TestCase):
    """page_script_bundles(): the table bundle only where a page has a
    scrollable table, the full-search bundle only on search.html — so the
    generated pages download only the JavaScript they use."""

    def test_search_page_only_on_search(self):
        self.assertEqual(build.page_script_bundles("search", "<div></div>"), ["search-page"])
        self.assertEqual(build.page_script_bundles("clause-9-web", "<div></div>"), [])

    def test_tables_only_when_a_table_wrap_is_present(self):
        self.assertEqual(build.page_script_bundles("clause-9-web",
                         '<div class="table-wrap"><table></table></div>'), ["tables"])
        self.assertEqual(build.page_script_bundles("index", "<p>no tables here</p>"), [])

    def test_generated_pages_load_only_needed_bundles(self):
        docs = ROOT / "docs"
        index = (docs / "index.html").read_text(encoding="utf-8")
        clause9 = (docs / "clause-9-web.html").read_text(encoding="utf-8")
        search = (docs / "search.html").read_text(encoding="utf-8")
        # main loads everywhere; search-page never on a clause page; tables
        # never on the table-free homepage.
        self.assertRegex(index, r"assets/js/main\.[0-9a-f]{8}\.js")
        self.assertNotIn("search-page.", index)
        self.assertNotIn("tables.", index)
        self.assertNotIn("search-page.", clause9)
        self.assertRegex(clause9, r"assets/js/tables\.[0-9a-f]{8}\.js")
        self.assertRegex(search, r"assets/js/search-page\.[0-9a-f]{8}\.js")

    def test_all_scripts_are_deferred(self):
        html_text = (ROOT / "docs" / "clause-9-web.html").read_text(encoding="utf-8")
        scripts = re.findall(r"<script src=[^>]+>", html_text)
        self.assertTrue(scripts)
        for tag in scripts:
            self.assertIn("defer", tag)


class SearchIndexTests(unittest.TestCase):
    """The two generated search indexes: a full-text index (search.html)
    and a small, body-free suggestion index (header box)."""

    FULL = json.loads((ROOT / "docs" / "search-index.json").read_text(encoding="utf-8"))
    SUGGEST = json.loads((ROOT / "docs" / "search-suggestions.json").read_text(encoding="utf-8"))

    def test_full_index_has_body_text(self):
        self.assertTrue(all("b" in e for e in self.FULL))
        self.assertTrue(any(e["b"] for e in self.FULL))

    def test_suggestion_index_drops_body_and_is_smaller(self):
        for e in self.SUGGEST:
            self.assertEqual(set(e), {"t", "p", "u"})
        suggest_bytes = (ROOT / "docs" / "search-suggestions.json").stat().st_size
        full_bytes = (ROOT / "docs" / "search-index.json").stat().st_size
        self.assertLess(suggest_bytes, full_bytes)

    def test_same_entry_count_so_suggestions_cover_everything(self):
        self.assertEqual(len(self.SUGGEST), len(self.FULL))

    def test_required_fields_present(self):
        for e in self.SUGGEST:
            self.assertIsInstance(e["t"], str)
            self.assertIsInstance(e["u"], str)


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

    def test_form_action_is_collected_but_data_attributes_are_not(self):
        html_text = ('<form action="search.html"></form>'
                     '<button data-action="print">x</button>'
                     '<div data-href="a.html" data-src="b.js">y</div>')
        self.assertEqual(self.urls(html_text), ["search.html"])


class AbsolutiseLocalLinksTests(unittest.TestCase):
    """absolutise_local_links(): the 404 page's URL rewriter. It must
    rewrite only genuine URL attributes (href, src, <form> action) and
    never data-*, aria-* or any attribute merely ending in one of those
    names — the old substring regex corrupted data-action="print" into
    an absolute URL, breaking the Print/Copy enhancements on 404.html."""

    BASE = "https://example.org/site/"

    def go(self, html_text):
        return build.absolutise_local_links(html_text, self.BASE)

    def test_relative_href_becomes_absolute(self):
        self.assertEqual(self.go('<a href="index.html">Home</a>'),
                         f'<a href="{self.BASE}index.html">Home</a>')

    def test_relative_src_becomes_absolute(self):
        self.assertEqual(self.go('<script src="assets/js/site.js"></script>'),
                         f'<script src="{self.BASE}assets/js/site.js"></script>')

    def test_form_action_becomes_absolute(self):
        self.assertEqual(self.go('<form action="search.html"><input></form>'),
                         f'<form action="{self.BASE}search.html"><input></form>')

    def test_data_action_values_stay_exactly_as_authored(self):
        for value in ("print", "copy-link", "bookmark"):
            html_text = f'<button type="button" data-action="{value}">x</button>'
            self.assertEqual(self.go(html_text), html_text)

    def test_data_href_data_src_and_aria_attributes_are_untouched(self):
        html_text = ('<div data-href="a.html" data-src="b.js" '
                     'aria-label="src of truth" data-extraction="x.html">y</div>')
        self.assertEqual(self.go(html_text), html_text)

    def test_action_outside_a_form_is_not_rewritten(self):
        html_text = '<button action="do.html">x</button>'
        self.assertEqual(self.go(html_text), html_text)

    def test_absolute_and_special_scheme_urls_are_untouched(self):
        html_text = ('<a href="https://example.org/x">a</a>'
                     '<a href="http://example.org/x">b</a>'
                     '<a href="mailto:x@example.org">c</a>'
                     '<a href="tel:+6400000000">d</a>'
                     '<img src="data:image/gif;base64,R0lGOD" alt="">'
                     '<a href="//example.org/x">e</a>')
        self.assertEqual(self.go(html_text), html_text)

    def test_fragment_only_links_are_untouched(self):
        html_text = '<a href="#main-content">Skip</a><a href="#top">Top</a>'
        self.assertEqual(self.go(html_text), html_text)

    def test_query_strings_and_fragments_are_preserved(self):
        self.assertEqual(self.go('<a href="a.html?q=1&amp;r=2#frag">x</a>'),
                         f'<a href="{self.BASE}a.html?q=1&amp;r=2#frag">x</a>')

    def test_attribute_order_and_boolean_attributes_survive(self):
        self.assertEqual(self.go('<input type="image" src="i.png" hidden required>'),
                         f'<input type="image" src="{self.BASE}i.png" hidden required>')

    def test_existing_escaped_values_are_escaped_exactly_once(self):
        out = self.go('<a href="a.html" title="A &amp; B">x</a>')
        self.assertIn('title="A &amp; B"', out)
        self.assertNotIn("&amp;amp;", out)

    def test_tags_without_local_urls_pass_through_byte_identical(self):
        # Includes case-sensitive SVG attributes and self-closing tags,
        # which only survive because untouched tags are never rebuilt.
        html_text = ('<svg viewBox="0 0 24 24" fill="none">'
                     '<path d="M6 9V3h12v6"/></svg>'
                     '<button data-action="print">Print</button>')
        self.assertEqual(self.go(html_text), html_text)

    def test_malformed_html_does_not_crash_and_still_rewrites_what_parses(self):
        out = self.go('<a href="x.html">unclosed <b><a href="#f">frag</a>')
        self.assertIn(f'href="{self.BASE}x.html"', out)
        self.assertIn('href="#f"', out)

    def test_rendered_404_page_carries_exact_data_actions(self):
        page = build.render_not_found_page(real_manifest())
        self.assertIn('data-action="print"', page)
        self.assertIn('data-action="copy-link"', page)
        self.assertNotIn('data-action="https://', page)

    def test_rendered_404_form_action_is_absolute(self):
        page = build.render_not_found_page(real_manifest())
        self.assertIn(f'action="{build.SITE_BASE_URL}search.html"', page)

    def test_validator_rejects_a_rewritten_data_action(self):
        errors = build.Errors()
        page = build.render_not_found_page(real_manifest()).replace(
            'data-action="print"', f'data-action="{build.SITE_BASE_URL}print"')
        build.validate_not_found_page(page, set(), errors)
        self.assertIn("404-data-action-rewritten",
                      [rule for _, rule, _, _ in errors.items])


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


class CssUrlReferenceTests(unittest.TestCase):
    """css_url_references(): every url(...) form a stylesheet can use."""

    def refs(self, text):
        return [u for u, _ in build.css_url_references(text)]

    def test_quoted_unquoted_relative_query_and_fragment_forms(self):
        css = ("@font-face { src: url('../fonts/a.woff2') format('woff2'); }\n"
               '.x { background: url("../img/b.png?v=1"); }\n'
               ".y { background: url(img/c.svg#frag); }\n"
               ".z { cursor: url( spaced.cur ); }\n")
        self.assertEqual(self.refs(css),
                         ["../fonts/a.woff2", "../img/b.png?v=1",
                          "img/c.svg#frag", "spaced.cur"])

    def test_data_and_external_https_urls_are_recognised(self):
        css = ('.a { background: url(data:image/gif;base64,R0lGOD); }\n'
               '.b { background: url("https://example.org/x.png"); }\n')
        self.assertEqual(self.refs(css),
                         ["data:image/gif;base64,R0lGOD", "https://example.org/x.png"])

    def test_line_numbers_are_reported(self):
        css = ".a{}\n.b { background: url(x.png); }\n"
        self.assertEqual(build.css_url_references(css), [("x.png", 2)])

    def test_committed_stylesheet_has_no_webfont_dependencies(self):
        # The site uses system fonts only: the committed stylesheet must
        # carry no @font-face and no local url() dependency (so no page
        # ever makes a font request). data:/https url()s would be allowed,
        # but the committed CSS currently has none at all.
        css = (ROOT / "assets" / "css" / "style.css").read_text(encoding="utf-8")
        self.assertNotIn("@font-face", css)
        self.assertNotIn(".woff2", css)
        local = [u for u in self.refs(css)
                 if not urllib.parse.urlsplit(u).scheme and not u.startswith("//")]
        self.assertEqual(local, [])


class CssResourceValidationTests(unittest.TestCase):
    """validate_css_resources(): local url(...) dependencies must exist
    in the published tree; ../ escapes and root-absolute paths are
    rejected; data:/https URLs are out of scope."""

    CSS = ("@font-face { src: url('../fonts/a.woff2') format('woff2'); }\n"
           '.x { background: url("../img/b.png?v=1"); }\n'
           ".ok { background: url(data:image/gif;base64,R0lGOD); }\n"
           ".ext { background: url(https://example.org/x.png); }\n")

    def validate(self, files):
        errors = build.Errors()
        with tempfile.TemporaryDirectory() as directory:
            staging = Path(directory)
            for rel, content in files.items():
                path = staging / rel
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(content, encoding="utf-8")
            published = build.published_files({}, staging)
            build.validate_css_resources(staging, published, errors)
        return errors.items

    def rules(self, files):
        return [rule for _, rule, _, _ in self.validate(files)]

    def test_valid_references_pass(self):
        self.assertEqual(self.rules({
            "assets/css/style.css": self.CSS,
            "assets/fonts/a.woff2": "f",
            "assets/img/b.png": "i",
        }), [])

    def test_missing_font_fails_and_guidance_points_at_assets_source(self):
        items = self.validate({
            "assets/css/style.css": self.CSS,
            "assets/img/b.png": "i",
        })
        self.assertEqual([rule for _, rule, _, _ in items], ["css-missing-resource"])
        _, _, message, fix = items[0]
        self.assertIn("assets/fonts/a.woff2", message)
        self.assertIn("assets/", fix)
        self.assertIn("Never hand-edit docs/", fix)

    def test_deleting_a_referenced_local_asset_fails(self):
        # Defence-in-depth for any future local CSS dependency (e.g. a
        # background image): a url() whose target is not published fails
        # the build. (The site currently self-hosts no fonts and no local
        # CSS assets, so this uses a representative synthetic stylesheet.)
        items = self.validate({
            "assets/css/style.css": '.x { background: url("../img/hero.png"); }\n',
        })
        self.assertEqual([rule for _, rule, _, _ in items], ["css-missing-resource"])
        self.assertIn("assets/img/hero.png", items[0][2])

    def test_tree_escape_and_root_absolute_are_rejected(self):
        self.assertEqual(
            self.rules({"assets/css/style.css": ".x{background:url(../../../outside.png)}"}),
            ["css-invalid-local-url"])
        self.assertEqual(
            self.rules({"assets/css/style.css": ".x{background:url(/rooted.png)}"}),
            ["css-invalid-local-url"])

    def test_unknown_scheme_is_rejected(self):
        self.assertEqual(
            self.rules({"assets/css/style.css": ".x{background:url(ftp://example.org/x)}"}),
            ["css-unsupported-url-scheme"])


class MissingResourceGuidanceTests(unittest.TestCase):
    """missing_resource_fix(): the error guidance must point at the
    hand-authored source (assets/, source/, deployment/cloudflare/) or
    the build code — never at editing the generated docs/ tree."""

    def test_each_target_kind_points_at_its_source(self):
        self.assertIn("assets/", build.missing_resource_fix("assets/img/x.png"))
        self.assertIn("source/", build.missing_resource_fix("source/x.pdf"))
        self.assertIn("deployment/cloudflare/", build.missing_resource_fix("_headers"))
        self.assertIn("scripts/build.py", build.missing_resource_fix("missing-page.html"))

    def test_guidance_always_forbids_hand_editing_docs(self):
        for target in ("assets/img/x.png", "source/x.pdf", "_redirects", "gone.html"):
            fix = build.missing_resource_fix(target)
            self.assertIn("Never hand-edit docs/", fix)
            self.assertNotIn("add the missing file under docs/", fix)


class SiteNameRenderingTests(unittest.TestCase):
    """The visible wordmark and site metadata are generated from the
    configured siteName, escaped for their contexts — never hardcoded
    and never trusted as HTML."""

    def test_camel_case_pair_keeps_the_accent_treatment(self):
        self.assertEqual(
            build.build_wordmark("AccessibleDocs"),
            '<span class="site-wordmark">Accessible'
            '<span class="site-wordmark__accent">Docs</span></span>')

    def test_other_names_render_as_plain_escaped_text(self):
        self.assertEqual(
            build.build_wordmark('Docs & "Standards" <Online>\''),
            '<span class="site-wordmark">Docs &amp; &quot;Standards&quot; '
            '&lt;Online&gt;&#x27;</span>')

    def test_unicode_names_pass_through_unmangled(self):
        self.assertEqual(build.build_wordmark("Café Docs"),
                         '<span class="site-wordmark">Café Docs</span>')

    def test_no_accent_is_invented_for_unsplittable_names(self):
        for name in ("AccessibleDocsOnline", "accessibledocs", "ACCESSIBLE",
                     "Accessible Docs"):
            self.assertNotIn("site-wordmark__accent", build.build_wordmark(name))

    def test_generated_pages_derive_the_wordmark_from_configuration(self):
        page = (ROOT / "docs" / "index.html").read_text(encoding="utf-8")
        self.assertIn(build.build_wordmark(build.SITE_NAME), page)

    def test_og_site_name_carries_the_configured_site_name(self):
        page = (ROOT / "docs" / "index.html").read_text(encoding="utf-8")
        self.assertIn(f'property="og:site_name" content="{build.SITE_NAME} — '
                      f'{build.DOC_LABEL} Online"', page)

    def test_configuration_values_are_escaped_in_every_context(self):
        saved = build.SITE_NAME, build.DOC_LABEL
        build.SITE_NAME = 'A&B "N" <T>'
        build.DOC_LABEL = 'L\'abel & <Doc> "v" — ✓'
        try:
            title = build.build_site_title("")
            meta = build.build_social_meta("T", "D", "https://example.org/")
            stub = build.generate_accessibility_statement_stub()
        finally:
            build.SITE_NAME, build.DOC_LABEL = saved
        for out in (title, meta, stub):
            self.assertNotIn("<T>", out)
            self.assertNotIn("<Doc>", out)
            self.assertNotIn("&amp;amp;", out)  # no double escaping
        self.assertIn("&amp;", title)
        self.assertIn("✓", meta)
        # og:site_name must not contain a raw quote from the values
        og_site_name = re.search(r'og:site_name" content="([^"]*)"', meta).group(1)
        self.assertIn("&quot;", og_site_name)


class RepositoryDocumentUrlTests(unittest.TestCase):
    """Repository-document links are generated from the validated
    repositoryUrl + repositoryRef — no branch name is hand-typed in
    reader-facing content, and a rename changes every link at once."""

    METADATA = {"statusLastChecked": "2026-07-17",
                "sourcePdfPublicationDate": "2025-12"}

    def test_url_is_built_from_configuration(self):
        self.assertEqual(
            build.repository_document_url("docs-for-maintainers/accessibility-testing.md"),
            f"{build.REPOSITORY_URL}/blob/{build.REPOSITORY_REF}/"
            "docs-for-maintainers/accessibility-testing.md")

    def test_about_fragment_has_no_hand_typed_branch_names(self):
        fragment = (ROOT / "content" / "about.html").read_text(encoding="utf-8")
        self.assertNotIn("/blob/", fragment)
        self.assertIn("{{ACCESSIBILITY_TESTING_URL}}", fragment)

    def test_branch_rename_changes_every_generated_link_consistently(self):
        fragment = (ROOT / "content" / "about.html").read_text(encoding="utf-8")
        expected_links = fragment.count("{{ACCESSIBILITY_TESTING_URL}}")
        self.assertGreater(expected_links, 0)
        saved = build.REPOSITORY_REF
        build.REPOSITORY_REF = "renamed-main"
        try:
            out = build.substitute_tokens(fragment, self.METADATA, build.Errors())
        finally:
            build.REPOSITORY_REF = saved
        renamed = (f"{build.REPOSITORY_URL}/blob/renamed-main/"
                   "docs-for-maintainers/accessibility-testing.md")
        self.assertEqual(out.count(renamed), expected_links)
        self.assertNotIn("{{ACCESSIBILITY_TESTING_URL}}", out)
        self.assertNotIn(f"/blob/{saved}/", out)

    def test_committed_docs_carry_the_configured_ref(self):
        page = (ROOT / "docs" / "about.html").read_text(encoding="utf-8")
        self.assertIn(f"{build.REPOSITORY_URL}/blob/{build.REPOSITORY_REF}/"
                      "docs-for-maintainers/accessibility-testing.md", page)


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
        "repositoryRef": "main",
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

    def test_repository_ref_valid_forms(self):
        for ref in ("main", "claude/pdf-accessible-website-j88o8l",
                    "release-1.2_x", "a/b/c"):
            self.assertEqual(self.rules(repositoryRef=ref), [], ref)

    def test_repository_ref_unsafe_values_are_rejected(self):
        for bad in ("feature?x=1", "feature#frag", "a b", "a\\b", "/rooted",
                    "trailing/", "a//b", "../escape", "dot/.hidden", "a..b",
                    "%2e%2e", 'quote"mark'):
            self.assertEqual(self.rules(repositoryRef=bad),
                             ["site-config-repository-ref-invalid"], bad)

    def test_missing_repository_ref_is_rejected(self):
        self.assertEqual(self.rules(repositoryRef=None),
                         ["site-config-missing-field"])

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
        self.assertEqual(build.REPOSITORY_REF, committed["repositoryRef"])
        self.assertEqual(build.SITE_NAME, committed["siteName"])
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
    # A minimal but valid IIFE module, one per JS bundle member.
    JS_MODULE = '(function () {\n  "use strict";\n})();\n'

    @contextlib.contextmanager
    def fake_site(self):
        """A minimal source tree + patched build-module globals, so
        publish_output() can run end to end against temp directories. The
        stylesheet and JS bundle modules are real source the build
        minifies and fingerprints; images are copied verbatim."""
        saved = {name: getattr(build, name) for name in
                 ("ASSETS_DIR", "SOURCE_DIR", "DEPLOYMENT_DIR", "SOURCE_PDF_PATH",
                  "SITEMAP", "CSS_DIR", "JS_DIR", "CSS_PATH")}
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            assets = root / "assets"
            for rel in ("img/favicon.svg", "img/favicon-32.png", "img/apple-touch-icon.png"):
                path = assets / rel
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("asset: " + rel, encoding="utf-8")
            (assets / "css").mkdir(parents=True, exist_ok=True)
            (assets / "css" / "style.css").write_text("body { color: #1a1a1a; }\n", encoding="utf-8")
            (assets / "js").mkdir(parents=True, exist_ok=True)
            for modules in build.JS_BUNDLES.values():
                for module in modules:
                    (assets / "js" / module).write_text(self.JS_MODULE, encoding="utf-8")
            source = root / "source"
            source.mkdir()
            (source / build.SOURCE_PDF_NAME).write_bytes(self.PDF_BYTES)
            deployment = root / "deployment"
            deployment.mkdir()
            (deployment / "_headers").write_text("/*\n  X-Frame-Options: DENY\n", encoding="utf-8")
            (deployment / "_redirects").write_text("# no active rules\n", encoding="utf-8")
            docs = root / "docs"
            build.ASSETS_DIR = assets
            build.CSS_DIR = assets / "css"
            build.JS_DIR = assets / "js"
            build.CSS_PATH = assets / "css" / "style.css"
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
        manifest, asset_files = build.compute_assets(errors)
        return build.publish_output(rendered, collected, [], manifest, asset_files, errors,
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

    def test_generated_assets_and_deployment_files_are_published(self):
        with self.fake_site() as (root, docs):
            manifest, _ = build.compute_assets(build.Errors())
            self.publish(docs)
            # CSS/JS are minified + fingerprinted (not copied verbatim);
            # the source style.css and unhashed names never appear.
            self.assertTrue((docs / manifest["style"]).is_file())
            self.assertTrue((docs / manifest["main"]).is_file())
            self.assertFalse((docs / "assets" / "css" / "style.css").exists())
            # Images are copied verbatim.
            self.assertEqual((docs / "assets" / "img" / "favicon.svg").read_text(encoding="utf-8"),
                             "asset: img/favicon.svg")
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
            _manifest, asset_files = build.compute_assets(build.Errors())
            self.publish(docs)
            actual = {p.relative_to(docs).as_posix() for p in docs.rglob("*") if p.is_file()}
            expected = (
                {f'{page["slug"]}.html' for page in build.SITEMAP}
                | set(build.GENERATED_EXTRA_FILES) | {".nojekyll"}
                | set(build.DEPLOYMENT_FILES)
                | set(asset_files)  # the fingerprinted CSS/JS bundles
                | {f"assets/img/{name}" for name in
                   ("favicon.svg", "favicon-32.png", "apple-touch-icon.png")}
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

    @contextlib.contextmanager
    def failing_backup_cleanup(self):
        """Make shutil.rmtree fail for .docs-old-* backup trees only."""
        real_rmtree = build.shutil.rmtree
        def failing(path, *args, **kwargs):
            if ".docs-old-" in str(path):
                raise OSError("simulated cleanup failure")
            return real_rmtree(path, *args, **kwargs)
        build.shutil.rmtree = failing
        try:
            yield
        finally:
            build.shutil.rmtree = real_rmtree

    def backup_dirs(self, root):
        return [p for p in root.iterdir() if p.name.startswith(".docs-old-")]

    def test_backup_cleanup_failure_is_a_warning_not_a_build_failure(self):
        with self.fake_site() as (root, docs):
            self.publish(docs)
            with self.failing_backup_cleanup():
                with contextlib.redirect_stderr(io.StringIO()) as err:
                    self.assertTrue(self.publish(docs))
            # the publication succeeded and docs/ is the NEW tree
            self.assertTrue((docs / "index.html").is_file())
            self.assertTrue((docs / "404.html").is_file())
            # the undeletable backup is retained and named in the warning
            leftovers = self.backup_dirs(root)
            self.assertEqual(len(leftovers), 1)
            self.assertIn("could not remove the pre-build backup", err.getvalue())
            self.assertIn(leftovers[0].name, err.getvalue())
            self.assertIn("rm -rf", err.getvalue())

    def test_later_build_removes_a_stale_backup(self):
        with self.fake_site() as (root, docs):
            self.publish(docs)
            with self.failing_backup_cleanup():
                with contextlib.redirect_stderr(io.StringIO()):
                    self.publish(docs)
            self.assertEqual(len(self.backup_dirs(root)), 1)
            # a stale backup from an "earlier run" (different pid) too
            stale = root / ".docs-old-99999999"
            stale.mkdir()
            (stale / "junk.html").write_text("junk", encoding="utf-8")
            self.publish(docs)
            self.assertEqual(self.backup_dirs(root), [])
            self.assertTrue((docs / "index.html").is_file())

    def test_cleanup_failure_never_touches_the_new_docs(self):
        with self.fake_site() as (root, docs):
            self.publish(docs)
            with self.failing_backup_cleanup():
                with contextlib.redirect_stderr(io.StringIO()):
                    self.publish(docs)
            manifest, _ = build.compute_assets(build.Errors())
            published = {p.relative_to(docs).as_posix() for p in docs.rglob("*") if p.is_file()}
            self.assertIn("index.html", published)
            self.assertIn(manifest["style"], published)


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
        # fingerprinted stylesheet: assets/css/style.<hash>.css
        self.assertRegex(self.PAGE, r'assets/css/style\.[0-9a-f]{8}\.css')

    def test_data_action_attributes_survive_absolutisation_exactly(self):
        self.assertIn('data-action="print"', self.PAGE)
        self.assertIn('data-action="copy-link"', self.PAGE)
        self.assertNotIn('data-action="https://', self.PAGE)

    def test_header_search_form_action_is_absolute(self):
        self.assertIn(f'action="{build.SITE_BASE_URL}search.html"', self.PAGE)


if __name__ == "__main__":
    unittest.main()
