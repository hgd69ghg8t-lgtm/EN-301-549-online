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


if __name__ == "__main__":
    unittest.main()
