import hashlib
import tempfile
import unittest
from pathlib import Path

from scripts import build


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


if __name__ == "__main__":
    unittest.main()
