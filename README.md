# EN 301 549 Online

An HTML edition of 'ETSI EN 301 549 V4.1.0: Accessibility requirements for ICT products and services' — a **final draft under approval, not yet a published standard** — designed and tested with the aim of meeting WCAG 2.2 Level AA. Styled with tokens from the [NZ Government Design System](https://github.com/GOVTNZ/govtnz-design-system) and structured similarly to [legislation.govt.nz](https://www.legislation.govt.nz/act/public/1991/69/en/latest/) (one page per clause/annex, a single persistent left-hand contents sidebar covering both the site-wide page list and the current page's own subsections, prev/next navigation).

**Before treating this project as ready for public release, read [Licensing, copyright and publication readiness](#licensing-copyright-and-publication-readiness) below.**

## Project structure

```
content/            37 body-only HTML fragments — the actual transcribed
                     standard text (headings, paragraphs, lists, tables,
                     callouts), plus this site's own homepage/about/search
                     pages (the About page includes the accessibility
                     statement). This is what you hand-edit.
                     Every fragment is clearly split into two kinds of text:
                     website-authored (introductions, "About this clause"
                     boxes, notices, navigation) and text reproduced
                     verbatim from the ETSI draft. See "Content-authoring
                     conventions" below for the rule about never editing
                     the latter.
data/
  source-metadata.json  Machine-readable source/version metadata (title,
                     version, status, source PDF URL, publication date,
                     download date, checksum). Rendered onto the About
                     page at build time, both as a plain-language summary
                     and (in a collapsible "Technical provenance" section)
                     the underlying checksum and file details.
  clause-summaries.json  The short, website-authored "About this clause"/
                     "About this annex" orientation text shown near the
                     top of every clause and annex page. Keyed by slug;
                     validated at build time (see "Validation" below).
scripts/
  build.py           The build script: validates content, then wraps each
                     content/ fragment in the shared page template (skip
                     link, header with search and quick links, breadcrumb,
                     contents sidebar, prev/next pager, footer) and writes
                     docs/*.html plus the search index,
                     sitemap.xml and robots.txt.
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
docs-for-maintainers/  Manual (non-automatable) testing documentation,
                     routine maintenance tasks (maintenance.md), and the
                     content-ownership/periodic-review record.
.github/workflows/   CI: build, validate, and accessibility-test every
                     push and pull request.
```

## Which files are source of truth, and how to rebuild

**Hand-edit:** everything under `content/`, `data/source-metadata.json`, `data/clause-summaries.json`, `data/content-ownership.json`, `scripts/sitemap.json`, `docs/assets/css/style.css`, `docs/assets/js/site.js`, `docs/assets/fonts/`, `docs/assets/img/` (the AccessibleDocs logo and favicons), `README.md`, and everything under `docs-for-maintainers/`. `data/etsi-content-hashes.json` is the one exception: it's committed, but it's only ever written by `scripts/update_etsi_hashes.py` (see "Reproduced ETSI wording integrity" below), never by hand.

**Generated — never hand-edit:** every other file directly under `docs/` (`docs/*.html`, `docs/search-index.json`, `docs/sitemap.xml`, `docs/robots.txt` — including `docs/accessibility-statement.html`, kept as a generated redirect to the About page so old links still work). They are committed to the repository (GitHub Pages serves straight from `docs/` with no build step of its own), but they are output, not input. If you edit a generated `docs/*.html` file directly, the next `python3 scripts/build.py` run will silently overwrite your change — and separately, `git diff --exit-code -- docs/` after a rebuild (see below) will show your manual edit as a difference the moment anyone rebuilds, so it can't quietly become the "real" version of the page. `scripts/build.py` never reads any *generated* file: the only things it reads under `docs/` are the hand-authored assets (`docs/assets/css/style.css` and `docs/assets/js/site.js`, hashed for the cache-busting `?v=` asset URLs) and the committed source PDF's size — so nothing that happens to already-committed `docs/*.html` can feed back into the next build.

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

If that `git diff` reports changes, `docs/` was out of date with `content/`/`scripts/sitemap.json`/`data/source-metadata.json` — rebuild and commit the difference. The build does not inject a live timestamp or any other run-to-run-varying value into generated pages, specifically so this comparison is meaningful: a clean rebuild from unchanged source always produces byte-identical output. [`.github/workflows/ci.yml`](.github/workflows/ci.yml) runs exactly this check on every push — it only ever fails the build if a difference is found, and never itself commits, amends, or overwrites `docs/` (no rebuild/commit loop).

### Reproduced ETSI wording integrity

`data/etsi-content-hashes.json` records a hash of the reproduced text in every clause/annex `content/*.html` file (every sitemap page except the website-authored `index`/`about`/`search`). The build recomputes and compares these hashes on every run, so an accidental (or unnoticed, e.g. from a bad merge) change to reproduced ETSI wording fails the build and names the exact file affected.

The hash is computed over the file's text content only, with all markup stripped and whitespace collapsed first — so changing a heading's level, id, or class, reindenting a file, or any other purely structural edit never trips this check; only a change to the actual reproduced words does.

The baseline is never updated automatically. If you have a genuine reason to change it — most likely, correcting an actual transcription error against the source PDF — run:

```
python3 scripts/update_etsi_hashes.py
```

and explain what you changed and why in your commit message. Do not run this just to make a validation failure go away without first checking why the wording changed.

To extract new content from the source PDF, you'll also need [`pdftotext`](https://poppler.freedesktop.org/) (from the `poppler-utils` package — not installed by default on a clean machine):

```
apt-get install poppler-utils   # Debian/Ubuntu
brew install poppler            # macOS
```

## Content-authoring conventions

- **Never rewrite, simplify, correct, paraphrase or otherwise change wording reproduced from the ETSI EN 301 549 standard.** That text must stay faithful to the source document. The only things it's safe to edit are website-authored material: introductions, summaries, explanatory text, navigation labels, link text, notices, the accessibility statement, the About page, source labels, metadata presentation, and headings created specifically for this website (not ETSI's own clause headings).
- Content fragments are body-only: no `<html>`, `<head>`, or `<body>` tags — the build template supplies those.
- **Do not put an `<h1>` in a content fragment.** Every page's `<h1>` — including the homepage's — comes from its `title` in `scripts/sitemap.json`, rendered in the blue document header band. The build fails if any fragment contains its own `<h1>`.
- **Numbered headings get their id from their clause number, never from their wording.** A heading whose visible text starts with a clause reference (e.g. `9.1.1.1 Non-text content`, `C.8.2.1.1 Speech volume gain`, `ZB.2 User interface...`) must have `id="9-1-1-1"` / `id="c-8-2-1-1"` / `id="zb-2"` — the number with dots turned into hyphens, nothing else. This is enforced at build time; a mismatch fails the build with the exact expected id. The reason for this rule: a link to a numbered heading then stays correct even if that heading's descriptive wording is later corrected, since the id never depended on the wording in the first place.
- Headings that aren't numbered (e.g. "Foreword", "Introduction") keep a hand-chosen, meaningful id — the build does not invent one from wording, since that would just move the instability problem rather than solve it.
- After adding or renumbering headings, run `python3 scripts/normalize_content.py` to bring every id in `content/` in line with the rule above in one pass, then rebuild.
- Every numbered heading (h2/h3/h4) automatically becomes its own permalink at build time: the heading's text is wrapped in a self-referencing link (one keyboard tab stop whose accessible name is the heading text itself — no separate "#" control), which navigates to the heading's anchor and, with JavaScript, also copies the deep link. You don't add this by hand in content fragments.
- Heading levels should not skip (an `<h3>` should not be followed directly by an `<h4>`'s child, i.e. by an `<h5>`, without an intervening `<h4>` on the way down). The build fails on a skipped level.
- A page with 2 or more h2/h3 headings automatically gets an "On this page" jump list at build time, generated from those headings — nothing to add by hand. Its depth is deliberately capped at h2/h3 (the same two levels the left-hand sidebar shows) — h4 requirement-level headings are excluded even on the longest pages, since listing every one of them (up to ~100+ on the biggest clauses) would make the list unusable rather than helpful. Website-only headings ("About this clause", "On this page" itself, etc.) are never included — `build_on_this_page()` only ever sees the fragment's own parsed ETSI headings, and this is re-checked on the final rendered output (see `on-this-page-utility-heading` in the validator).
- Every clause and annex page has a short "About this clause"/"About this annex" orientation box, kept in `data/clause-summaries.json` keyed by slug. Keep each to 1–2 short paragraphs, and describe what the clause covers without interpreting conformance requirements, adding obligations, or narrowing scope. The build automatically appends the fixed "reproduced from the ETSI draft, not simplified or changed" sentence; don't duplicate it in the JSON. To state that a part is normative or informative, set the optional `"nature": "normative"` / `"informative"` field — the build appends the standard "It is normative/informative, which means …" sentence from one place, so its wording can't drift between entries. You can also link the words "normative" or "informative" to their definition on the About page by writing `{{normative}}` / `{{informative}}` in free text.
- Cross-references in the reproduced text — "see clause 5.1.3", "clauses 9, 10 and 11", "Annex ZA", bibliography citations like "[i.25]" — are turned into links automatically at build time (`link_cross_references()` in `scripts/build.py`). This is markup only: no wording changes (the wording-integrity check would fail if it did), text already inside a link, heading, or table caption is never touched, and anything the build can't resolve to a certain target is left as plain text — e.g. "Annex I", which belongs to an EU Directive, not this document. Clause 2's bibliography entries get stable `ref-…` ids so citations can deep-link to them.
- The site search is entirely static: the build writes `docs/search-index.json` (one entry per heading section, glossary term, and page intro — deterministic, so reproducible builds still hold), and `docs/assets/js/site.js` filters it in the browser on `search.html`. No search service, no third-party library. Nothing to maintain by hand — the index regenerates from content on every build.
- On narrow viewports the header search collapses to a magnifier icon button that opens the form full-width below the header row (focus moves into the input; Escape closes). This collapse is gated on the `.js` class: without JavaScript the plain GET form stays permanently visible, so searching never requires script.
- With JavaScript, the header search also offers instant suggestions (an ARIA combobox listbox of the top matches — arrow keys to review, Enter to follow, Escape to dismiss without losing the typed text), and a followed result carries the query as a `?h=` parameter so the destination page highlights the matched words client-side (`<mark>` wrapping only — the generated HTML on disk never changes, and the parameter is removed from the address bar after use). Without JavaScript the form still submits to `search.html` as a plain GET.
- A handful of `{{TOKEN}}` placeholders are available in content fragments for values `scripts/build.py` can compute reliably (so they can never go stale): `{{STATUS_LAST_CHECKED}}`, `{{SOURCE_MONTH_YEAR}}`, `{{SOURCE_PDF_SIZE}}`. See `substitute_tokens()` in `scripts/build.py` for the full list. The build fails if an unreplaced `{{...}}` token would be published.
- Reader-facing dates use human formatting ("13 July 2026", "June 2026"), not ISO (`2026-07-13`) — `human_date()` in `scripts/build.py` does this conversion for every date the build itself renders. This does not apply to dates that are part of reproduced ETSI content (e.g. Annex F's change-history table uses ETSI's own date format, and that must not be reformatted).
- The build fails if publishable placeholder text (e.g. `[insert a real contact method here]`) is found in generated output — don't leave TODO-style placeholders in content that's ready to ship.
- Every `<dt>` definition term in a fragment (clause 3's Terms and Abbreviations lists today) automatically gets a stable `id="def-..."` at build time — generated from the term's own text, deterministic across builds, never from its position in the list — plus `tabindex="-1"` so it can receive keyboard focus when linked to directly. Nothing to add by hand, and an existing hand-authored `id` on a `<dt>` is always kept as-is. A `<dl>` with `AZ_INDEX_THRESHOLD` (20) or more terms also gets a same-page A-Z index inserted before it and a "Back to A-Z index" link after it — see `apply_glossary_terms()` in `scripts/build.py`. This never restructures or reorders the definitions themselves.

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
- a same-page `href="#id"` with no matching id, or a same-site `href="....html"` with no matching page;
- unfilled placeholder text (e.g. `[insert a real contact method here]`) that would otherwise be published;
- an unreplaced `{{TOKEN}}` in generated output;
- a heading link wrapping no meaningful text (its accessible name is the heading text it wraps, so an empty one would be an unlabelled control);
- the accessibility statement missing a real reporting route (a GitHub issues link or a `mailto:` link);
- an "On this page" list containing a website-only utility heading instead of just the fragment's own ETSI headings;
- an invalid, missing, future-dated, or obviously-placeholder `statusLastChecked`/`dateDownloaded`;
- a `data/clause-summaries.json` entry that references a page that doesn't exist, has a duplicate key, is empty, contains raw HTML, is too long, or contains placeholder text;
- a `<dt>` glossary/abbreviation term rendered without a stable id, or two terms rendered with the same id;
- an A-Z index rendered with no letter links, letters not in alphabetical order, or a letter link pointing at an id that doesn't exist on the page;
- a clause number that appears as a heading on two different pages (cross-reference links to it would be ambiguous), or any cross-page `href="page.html#id"` — hand-authored or auto-generated — whose id doesn't exist on the target page;
- a `data/content-ownership.json` entry with an unrecognised page slug or field, or a `lastReviewDate`/`nextReviewDate`/`statusCheckDate` that's malformed or an obvious placeholder (a `null` value, meaning "not known yet", is always valid — see `docs-for-maintainers/content-ownership.md`);
- a clause/annex `content/*.html` file whose reproduced ETSI wording no longer matches its recorded integrity hash, or a missing/stale entry in `data/etsi-content-hashes.json` (see "Reproduced ETSI wording integrity" above).

## Accessibility

The site has light and dark themes: the OS preference applies automatically (`prefers-color-scheme`), and Reading options offers an explicit Light/Dark/Auto choice, persisted in the browser and applied before first paint by a small inline script. Theming is token-level only — the dark palette redefines the custom properties in `docs/assets/css/style.css`, and fixed white-text surfaces (the blue title band, navigation highlights, buttons) deliberately keep their colours in both themes. Colour pairs in **both** themes are verified against WCAG 2.2 AA contrast thresholds (4.5:1 text, 3:1 UI components) by `scripts/check-contrast.py`, which runs as part of `npm test`, and the axe sweep (`npm run test:a11y`) checks every page in both themes. This site is **designed and tested with the aim of meeting WCAG 2.2 Level AA** — that is a target, not an independently audited conformance certificate. See the [accessibility statement section of the About page](docs/about.html) (or `content/about.html` before building) for exactly what has been automated-tested, what still needs manual evaluation, and how to report a problem. Manual, non-automatable testing procedure and the test log live in [`docs-for-maintainers/accessibility-testing.md`](docs-for-maintainers/accessibility-testing.md).

## Testing

```
npm install
npm run build          # python3 scripts/build.py
npm test               # build + structural/content validation (no network, no browser)
npm run test:a11y      # axe-core against every generated page (requires a Chromium install)
npm run test:layout    # responsive layout assertions at 320-1920px (requires a Chromium install)
npm run test:search    # site-search end-to-end checks (requires a Chromium install)
```

`npm test` is pure Python + Node, no browser required, and is what should run on every commit. `npm run test:a11y` and `npm run test:layout` additionally need a Chromium binary; run `npx playwright install --with-deps chromium` once before the first local run. The layout test checks, on representative pages at seven viewport widths (320-1920px): no page-level horizontal overflow, no sidebar/content overlap, the content column actually growing on wider screens, table wrappers only scrolling when the table's measured minimum width genuinely exceeds the space, and the mobile contents disclosure still working. See [`.github/workflows/ci.yml`](.github/workflows/ci.yml) for exactly what runs in CI and why these tools specifically — see the comment at the top of that file.

## Maintenance

Routine maintenance tasks — updating the ETSI publication status, the status-check date, the source PDF link, clause summaries, the wording-integrity baseline, running the full test suite, reviewing the accessibility statement, recording manual testing, and more — are documented in [`docs-for-maintainers/maintenance.md`](docs-for-maintainers/maintenance.md).

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

**The repository's software licence does not necessarily apply to reproduced ETSI text.** Whatever licence is eventually chosen and recorded above governs the build script, templates, CSS and JavaScript — it says nothing about whether the reproduced standard text may be copied, redistributed, or reused, which is governed entirely by ETSI's own copyright notice and the unresolved permission question above. Confirm permission and applicable terms before redistributing or promoting this edition.

### Trademarks

The source document's own front matter — reproduced verbatim on the [About page](content/about.html#trademarks) — states that it may include trademarks and tradenames asserted or registered by their owners, that ETSI claims no ownership of these except where indicated, and that reproducing the document does not convey any right to use or reproduce those trademarks. That notice, and the specific trademark names it lists (DECT, PLUGTESTS, UMTS, 3GPP, LTE, 5G, oneM2M, GSM, BLUETOOTH, and others named there), must not be edited, summarised, or removed. Nothing in this repository's own code/design licence extends any right to use those names or logos.

### Font licences

The self-hosted webfonts under `docs/assets/fonts/` (Overpass and Source Sans 3, both distributed by Google Fonts) are released under the [SIL Open Font License 1.1](https://openfontlicense.org/), which permits embedding and redistribution, including in a project with different licensing terms for its other components. No separate action is required for these two fonts, but re-verify the licence of any font added later.

### Publication-readiness checklist

Do not treat this site as ready for public release until every item below is either checked or explicitly waived by whoever is accountable for that decision.

- [ ] **Reproduction rights confirmed** — see "The core open question" and "ETSI reproduction permission" above. *(Required — this is the one item on this list that is a precondition for every other item mattering.)*
- [ ] A licence has been chosen and recorded for this site's own code/design (see above), and it is clear anywhere that licence is stated (a `LICENSE` file, this README) that it does not extend to the reproduced ETSI text or to the trademarks named in it.
- [ ] `npm test` and `npm run test:a11y` both pass on the commit being published.
- [ ] `python3 scripts/build.py && git diff --exit-code -- docs/` is clean (committed `docs/` matches a fresh rebuild).
- [x] The accessibility statement has a real reporting route (currently a GitHub issues link — replace with a dedicated contact address if/when one exists).
- [ ] The accessibility statement's "Review history" section has at least one real, completed review recorded.
- [ ] A genuine manual accessibility test pass has been completed against `docs-for-maintainers/accessibility-testing.md`, and its log updated.
- [ ] `data/source-metadata.json`'s checksum has been re-verified against the currently committed source PDF.
