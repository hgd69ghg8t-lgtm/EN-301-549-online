# EN 301 549 Online

An HTML edition of *ETSI EN 301 549 V4.1.0: Accessibility requirements for ICT products and services* — a **final draft under approval, not yet a published standard** — designed and tested with the aim of meeting WCAG 2.2 Level AA. Styled with tokens from the [NZ Government Design System](https://github.com/GOVTNZ/govtnz-design-system) and structured similarly to [legislation.govt.nz](https://www.legislation.govt.nz/act/public/1991/69/en/latest/) (one page per clause/annex, a single persistent left-hand contents sidebar covering both the site-wide page list and the current page's own subsections, prev/next navigation).

**Before treating this project as ready for public release, read [Licensing, copyright and publication readiness](#licensing-copyright-and-publication-readiness) below.**

## Project structure

```
content/            36+ body-only HTML fragments — the actual transcribed
                     standard text (headings, paragraphs, lists, tables,
                     callouts), plus this site's own about/accessibility-
                     statement pages. This is what you hand-edit.
data/
  source-metadata.json  Machine-readable source/version metadata (title,
                     version, status, source PDF URL, publication date,
                     download date, SHA-256 checksum). Rendered onto the
                     About page at build time.
scripts/
  build.py           The build script: validates content, then wraps each
                     content/ fragment in the shared page template (skip
                     link, header, breadcrumb, contents sidebar, draft
                     notice, prev/next pager, footer) and writes docs/*.html.
  heading_parser.py  Shared HTML heading parser (Python's stdlib
                     html.parser — no third-party dependency) used by both
                     build.py and normalize_content.py.
  normalize_content.py  Maintenance tool: rewrites content/ fragments so
                     every numbered heading's id is derived from its clause
                     number. Run this after adding or renumbering headings.
  sitemap.json        Single source of truth for the site's pages: slug,
                     title, nav group, and the source PDF page range each
                     page was transcribed from. Annex ordering in the
                     contents sidebar is generated directly from this file
                     — there is no separate, second ordering list anywhere
                     else in the codebase.
docs/                Generated output, served by GitHub Pages. Never
                     hand-edited — re-run the build instead. Also holds the
                     static, hand-authored docs/assets/css/style.css and
                     docs/assets/js/site.js, and the self-hosted webfonts.
source/              The original ETSI source PDF (symlinked to
                     docs/source/, the copy GitHub Pages actually serves,
                     so the file is committed once, not twice).
design/              Figma Make export used as the visual reference for the
                     site's design system. Not read by the build.
docs-for-maintainers/  Manual (non-automatable) testing documentation.
.github/workflows/   CI: build, validate, and accessibility-test every
                     push and pull request.
```

## Which files are source of truth, and how to rebuild

**Hand-edit:** everything under `content/`, `data/source-metadata.json`, `scripts/sitemap.json`, `docs/assets/css/style.css`, `docs/assets/js/site.js`, `docs/assets/fonts/`, `README.md`, and everything under `docs-for-maintainers/`.

**Generated — never hand-edit:** every other file directly under `docs/` (`docs/*.html`). They are committed to the repository (GitHub Pages serves straight from `docs/` with no build step of its own), but they are output, not input. If you edit a generated `docs/*.html` file directly, the next `python3 scripts/build.py` run will silently overwrite your change.

The build has no dependencies beyond the Python 3 standard library:

```
python3 scripts/build.py
```

This reads `data/source-metadata.json`, `scripts/sitemap.json` and `content/*.html`, validates them (see [Validation](#validation-the-build-fails-on-invalid-content) below), and regenerates every file under `docs/`. **Re-run it after editing anything in `content/`, `data/source-metadata.json`, or `scripts/sitemap.json`, and commit the resulting `docs/` changes together with your source edit.**

To verify a change is valid without writing `docs/`:

```
python3 scripts/build.py --check-only
```

To verify the committed `docs/` output actually matches a clean rebuild from source (this is exactly what CI checks on every push):

```
python3 scripts/build.py
git diff --exit-code -- docs/
```

If that `git diff` reports changes, `docs/` was out of date with `content/`/`scripts/sitemap.json`/`data/source-metadata.json` — rebuild and commit the difference. The build does not inject a live timestamp or any other run-to-run-varying value into generated pages, specifically so this comparison is meaningful: a clean rebuild from unchanged source always produces byte-identical output.

To extract new content from the source PDF, you'll also need [`pdftotext`](https://poppler.freedesktop.org/) (from the `poppler-utils` package — not installed by default on a clean machine):

```
apt-get install poppler-utils   # Debian/Ubuntu
brew install poppler            # macOS
```

## Content-authoring conventions

- Content fragments are body-only: no `<html>`, `<head>`, or `<body>` tags — the build template supplies those.
- **Do not put an `<h1>` in a content fragment** (except `content/index.html`, the homepage, which has no template-level doc header and so owns the page's only `<h1>` itself). Every other page's `<h1>` comes from its `title` in `scripts/sitemap.json`. The build fails if a non-homepage fragment contains its own `<h1>`.
- **Numbered headings get their id from their clause number, never from their wording.** A heading whose visible text starts with a clause reference (e.g. `9.1.1.1 Non-text content`, `C.8.2.1.1 Speech volume gain`, `ZB.2 User interface...`) must have `id="9-1-1-1"` / `id="c-8-2-1-1"` / `id="zb-2"` — the number with dots turned into hyphens, nothing else. This is enforced at build time; a mismatch fails the build with the exact expected id. The reason for this rule: a link to a numbered heading then stays correct even if that heading's descriptive wording is later corrected, since the id never depended on the wording in the first place.
- Headings that aren't numbered (e.g. "Foreword", "Introduction") keep a hand-chosen, meaningful id — the build does not invent one from wording, since that would just move the instability problem rather than solve it.
- After adding or renumbering headings, run `python3 scripts/normalize_content.py` to bring every id in `content/` in line with the rule above in one pass, then rebuild.
- Every numbered heading (h2/h3/h4) automatically gets a small "#" permalink control next to it at build time — you don't add this by hand in content fragments.
- Heading levels should not skip (an `<h3>` should not be followed directly by an `<h4>`'s child, i.e. by an `<h5>`, without an intervening `<h4>` on the way down). The build fails on a skipped level.

## Validation: the build fails on invalid content

`python3 scripts/build.py` is also the validator — there is no separate step that can be skipped. It exits with a non-zero status, writes nothing to `docs/`, and prints the exact file, the rule that failed, and the fix, if it finds:

- a sitemap entry with no matching `content/*.html` fragment, or a content fragment with no matching sitemap entry;
- a missing, invalid, or incomplete `data/source-metadata.json`;
- more or fewer than exactly one non-empty `<h1>` on any generated page;
- a numbered heading whose id doesn't match its clause number;
- a heading (h2/h3) with no id at all;
- duplicate ids on the same page;
- a heading level that skips a level going deeper;
- malformed HTML (unclosed or mismatched tags);
- a same-page `href="#id"` with no matching id, or a same-site `href="....html"` with no matching page.

## Accessibility

Colour pairs are verified against WCAG 2.2 AA contrast thresholds (4.5:1 text, 3:1 UI components) — see `docs/assets/css/style.css` header comment for the source tokens. This site is **designed and tested with the aim of meeting WCAG 2.2 Level AA** — that is a target, not an independently audited conformance certificate. See the [accessibility statement](docs/accessibility-statement.html) (or `content/accessibility-statement.html` before building) for exactly what has been automated-tested, what still needs manual evaluation, and how to report a problem. Manual, non-automatable testing procedure and the test log live in [`docs-for-maintainers/accessibility-testing.md`](docs-for-maintainers/accessibility-testing.md).

## Testing

```
npm install
npm run build          # python3 scripts/build.py
npm test               # build + structural/content validation (no network, no browser)
npm run test:a11y      # axe-core against every generated page (requires a Chromium install)
```

`npm test` is pure Python + Node, no browser required, and is what should run on every commit. `npm run test:a11y` additionally needs a Chromium binary; run `npx playwright install --with-deps chromium` once before the first local run. See [`.github/workflows/ci.yml`](.github/workflows/ci.yml) for exactly what runs in CI, and why these two tools specifically — see the comment at the top of that file.

## Hosting

This site is published for free via GitHub Pages, serving from the `docs/` folder. Once this branch is merged to the default branch, enable it under **Settings → Pages → Source: Deploy from a branch → (default branch) /docs**.

## Licensing, copyright and publication readiness

**This section states facts and open questions. It does not make a legal determination, and nothing below should be read as one.**

### The core open question

The source PDF's own front matter (reproduced in full on the [About page](content/about.html)) states: *"No part may be reproduced or utilized in any form or by any means, electronic or mechanical, including photocopying and microfilm except as authorized by written permission of ETSI."* This repository republishes the full text of that document. **Whether ETSI's actual terms permit this kind of republication — and under what conditions — has not been confirmed and is not something this repository can resolve on its own.** Confirm this directly with ETSI (or with whoever owns publication decisions for this project) before treating the site as ready for public release.

### ETSI reproduction permission

Status: **not confirmed**. If and when permission, a licence, or another form of authorization is obtained, record it here:

- Permission/licence reference: `[not yet recorded]`
- Granted by / contact: `[not yet recorded]`
- Date granted: `[not yet recorded]`
- Scope and any conditions: `[not yet recorded]`

### Licence for this site's own code and design

The build script, templates, CSS and JavaScript in this repository (everything *other than* the reproduced ETSI standard text and the ETSI copyright/disclaimer notices) do not currently carry an explicit licence file. `[Add a LICENSE file and name it here once a licence is chosen — the reproduced standard text itself is governed by ETSI's own copyright notice regardless of what licence is chosen for the surrounding site code, and the two must not be conflated.]`

### Font licences

The self-hosted webfonts under `docs/assets/fonts/` (Overpass and Source Sans 3, both distributed by Google Fonts) are released under the [SIL Open Font License 1.1](https://openfontlicense.org/), which permits embedding and redistribution, including in a project with different licensing terms for its other components. No separate action is required for these two fonts, but re-verify the licence of any font added later.

### Publication-readiness checklist

Do not treat this site as ready for public release until every item below is either checked or explicitly waived by whoever is accountable for that decision.

- [ ] **Reproduction rights confirmed** — see "The core open question" and "ETSI reproduction permission" above. *(Required — this is the one item on this list that is a precondition for every other item mattering.)*
- [ ] A licence has been chosen and recorded for this site's own code/design (see above).
- [ ] `npm test` and `npm run test:a11y` both pass on the commit being published.
- [ ] `python3 scripts/build.py && git diff --exit-code -- docs/` is clean (committed `docs/` matches a fresh rebuild).
- [ ] The accessibility statement's placeholder contact method has been replaced with a real one.
- [ ] The accessibility statement's review-history table has at least one real entry, not just the placeholder row.
- [ ] `data/source-metadata.json`'s checksum has been re-verified against the currently committed source PDF.
