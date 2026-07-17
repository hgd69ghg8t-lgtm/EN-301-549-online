import hashlib
import re
import tempfile
import unittest
from pathlib import Path

from scripts import build

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

    CSS = (ROOT / "scripts" / "source" / "style.css").read_text(encoding="utf-8")
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
        expected = (build.THEME_SCRIPT
                    .replace("@LIGHT@", build.THEME_CHROME_LIGHT)
                    .replace("@DARK@", build.THEME_CHROME_DARK))
        self.assertIn(f"<script>{expected}</script>", self.PAGE)

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
    with the wrong tokens. The script itself is emitted pre-minified —
    the full rationale lives as a comment above THEME_SCRIPT in
    scripts/build.py and in the README, not repeated in every page.
    (Real first-paint behaviour is still worth an occasional manual look
    in real browsers.)"""

    PAGE = (ROOT / "docs" / "index.html").read_text(encoding="utf-8")

    def script(self):
        # The theme script is the page's first inline <script>.
        start = self.PAGE.index("<script>") + len("<script>")
        return self.PAGE[start:self.PAGE.index("</script>", start)]

    def test_theme_script_precedes_the_stylesheet(self):
        self.assertLess(self.PAGE.index("<script>"),
                        self.PAGE.index('<link rel="stylesheet"'))

    def test_theme_script_is_inline_and_synchronous(self):
        # The document's first script of any kind must be the bare inline
        # <script> (no src/defer/async attributes) — it has to run in
        # place, before the stylesheet is even discovered, and no
        # external script may be discovered ahead of it.
        self.assertEqual(self.PAGE.index("<script"), self.PAGE.index("<script>"))

    def test_theme_metas_precede_the_script(self):
        # the script writes to both metas, so they must already be parsed
        self.assertLess(self.PAGE.index('id="theme-colour-light"'),
                        self.PAGE.index("<script>"))

    def test_script_applies_the_theme_synchronously(self):
        script = self.script()
        self.assertIn('localStorage.getItem("accessibleDocs.readerPrefs.v1")', script)
        self.assertIn('document.documentElement.setAttribute("data-theme",t)', script)
        self.assertIn('window.__syncThemeColour(t||"auto")', script)

    def test_malformed_storage_cannot_break_rendering(self):
        # The storage read/parse is wrapped in try/catch and only the two
        # literal theme names are accepted — garbage in localStorage can
        # never set an attribute or throw before first paint.
        script = self.script()
        self.assertIn("try{", script)
        self.assertIn("catch(e){}", script)
        self.assertIn('p.theme==="dark"||p.theme==="light"', script)

    def test_script_needs_no_asynchronous_step(self):
        script = self.script()
        for forbidden in ("setTimeout", "setInterval", "requestAnimationFrame",
                          "addEventListener", ".then(", "await ", "Promise"):
            self.assertNotIn(forbidden, script,
                             f"pre-paint script must be synchronous; found {forbidden!r}")


class HtmlMinificationTests(unittest.TestCase):
    """minify_page_html() may only remove indentation and blank lines
    outside preformatted content — the whitespace-collapsed visible text
    must be identical before and after, and <pre>/<textarea> content must
    pass through byte-for-byte."""

    def test_strips_indentation_and_blank_lines(self):
        src = "<div>\n   <p>hello\n      world</p>\n\n</div>\n"
        out = build.minify_page_html(src)
        self.assertEqual(out, "<div>\n<p>hello\nworld</p>\n</div>\n")
        self.assertEqual(build.canonical_etsi_text(out), build.canonical_etsi_text(src))

    def test_preformatted_content_is_untouched(self):
        src = "<div>\n  <pre>\n   indented\n\n  kept</pre>\n  <p>after</p>\n</div>\n"
        out = build.minify_page_html(src)
        self.assertIn("\n   indented\n\n  kept</pre>", out)
        self.assertIn("<p>after</p>", out)
        self.assertNotIn("  <p>after</p>", out)

    def test_generated_pages_preserve_visible_text(self):
        # End-to-end on a real generated page: the committed docs/ page is
        # minified output; its canonical text must match a fresh render's.
        page = (ROOT / "docs" / "clause-9-web.html").read_text(encoding="utf-8")
        self.assertEqual(build.canonical_etsi_text(build.minify_page_html(page)),
                         build.canonical_etsi_text(page))


class HashedAssetTests(unittest.TestCase):
    """The content-hashed filename scheme: hashes derive from final
    production bytes, change exactly when the bytes change, and every
    generated page references only assets that exist."""

    def test_hash_is_deterministic_and_content_derived(self):
        self.assertEqual(build.content_hash("body{}"), build.content_hash("body{}"))
        self.assertNotEqual(build.content_hash("body{}"), build.content_hash("body{color:red}"))
        self.assertTrue(re.fullmatch(r"[0-9a-f]{8}", build.content_hash("x")))

    def test_changing_one_source_changes_only_that_filename(self):
        minified = {"style.css": "body{}", "core.js": "var a=1;"}
        before = build.hashed_asset_names(minified)
        after = build.hashed_asset_names({"style.css": "body{color:red}", "core.js": "var a=1;"})
        self.assertNotEqual(before["style.css"], after["style.css"])
        self.assertEqual(before["core.js"], after["core.js"])
        self.assertTrue(re.fullmatch(r"style\.[0-9a-f]{8}\.css", before["style.css"]))

    def test_generated_pages_reference_no_unhashed_or_stale_assets(self):
        docs = ROOT / "docs"
        on_disk = ({f"assets/css/{p.name}" for p in (docs / "assets" / "css").glob("*.css")} |
                   {f"assets/js/{p.name}" for p in (docs / "assets" / "js").glob("*.js")} |
                   {p.name for p in docs.glob("search-index*.json")} |
                   {p.name for p in docs.glob("search-suggestions*.json")})
        referenced = set()
        for page in docs.glob("*.html"):
            html_text = page.read_text(encoding="utf-8")
            for ref in build.collect_asset_refs(html_text):
                if ref.endswith((".css", ".js", ".json")):
                    referenced.add(ref)
                    self.assertIn(ref, on_disk,
                                  f"{page.name} references {ref}, which is not on disk")
        # ...and the reverse: nothing hashed on disk goes unreferenced.
        self.assertEqual(on_disk - referenced, set(),
                         "stale hashed production assets exist that no page references")

    def test_core_script_is_deferred_in_head(self):
        page = (ROOT / "docs" / "index.html").read_text(encoding="utf-8")
        head = page[:page.index("</head>")]
        self.assertRegex(head, r'<script defer src="assets/js/core\.[0-9a-f]{8}\.js"></script>')
        # and no script tag at the end of <body> any more
        body_tail = page[page.rindex("</footer>"):]
        self.assertNotIn("<script", body_tail)

    def test_tables_bundle_only_on_pages_with_tables(self):
        with_tables = (ROOT / "docs" / "clause-9-web.html").read_text(encoding="utf-8")
        without_tables = (ROOT / "docs" / "clause-4-functional-performance.html").read_text(encoding="utf-8")
        self.assertRegex(with_tables, r'assets/js/tables\.[0-9a-f]{8}\.js')
        self.assertNotIn("assets/js/tables.", without_tables)

    def test_ordinary_pages_never_name_the_full_search_index(self):
        ordinary = (ROOT / "docs" / "clause-9-web.html").read_text(encoding="utf-8")
        search_page = (ROOT / "docs" / "search.html").read_text(encoding="utf-8")
        self.assertNotIn("data-search-index", ordinary)
        self.assertIn("data-search-index", search_page)
        self.assertIn("data-search-worker", search_page)
        self.assertIn("data-suggest-index", ordinary)

    def test_no_production_webfonts(self):
        fonts_dir = ROOT / "docs" / "assets" / "fonts"
        woff2 = list(fonts_dir.glob("**/*.woff2")) if fonts_dir.exists() else []
        self.assertEqual(woff2, [], "production output must not ship webfont files")
        for page in (ROOT / "docs").glob("*.html"):
            self.assertNotIn(".woff2", page.read_text(encoding="utf-8"),
                             f"{page.name} references a webfont")
        css_files = list((ROOT / "docs" / "assets" / "css").glob("*.css"))
        for css in css_files:
            self.assertNotIn("@font-face", css.read_text(encoding="utf-8"),
                             f"{css.name} still declares a webfont")


if __name__ == "__main__":
    unittest.main()
