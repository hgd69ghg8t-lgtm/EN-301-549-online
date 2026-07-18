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
assets/             Hand-authored static assets: assets/css/style.css,
                     assets/js/site.js, the favicons/logo under
                     assets/img/, and the self-hosted webfonts under
                     assets/fonts/. The build copies this whole tree into
                     docs/assets/, so the public asset URLs are unchanged.
source/             The original ETSI source PDF (the source copy). The
                     build copies it into docs/source/, so the PDF stays
                     published at its existing URL. Never edit its bytes.
deployment/
  cloudflare/        Cloudflare Pages configuration source (_headers,
                     _redirects), copied by the build to docs/_headers
                     and docs/_redirects. Prepared for a possible later
                     Cloudflare Pages deployment; GitHub Pages ignores
                     these files. A Cloudflare Git integration has
                     attempted (and failed) a deployment; the site is
                     not confirmed as deployed on Cloudflare — see
                     docs-for-maintainers/cloudflare-pages.md.
data/
  site-config.json   The site's identity and deployment configuration:
                     site name (the header wordmark and og:site_name
                     are generated from it), document label, the
                     production base URL (canonical/Open Graph/sitemap
                     URLs all come from here), the repository URL, the
                     repository ref (the default branch name used to
                     build repository-document links such as the manual
                     testing log), and the deployment target. Strictly
                     validated at build time; changing the production
                     domain — or renaming the default branch — means
                     editing this one file, rebuilding, and re-running
                     the tests.
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
docs/                Generated output, served by GitHub Pages. ENTIRELY
                     generated — every file in it is either rendered by
                     the build or copied from assets/, source/ or
                     deployment/. Never hand-edit anything under docs/;
                     re-run the build instead.
design/              Figma Make export used as the visual reference for the
                     site's design system. Not read by the build.
docs-for-maintainers/  Manual (non-automatable) testing documentation,
                     routine maintenance tasks (maintenance.md), and the
                     content-ownership/periodic-review record.
.github/workflows/   CI: build, validate, and accessibility-test every
                     push and pull request.
```

## Which files are source of truth, and how to rebuild

**Hand-edit:** everything under `content/`, `assets/` (CSS, JavaScript, fonts, the AccessibleDocs logo and favicons), `deployment/cloudflare/`, `data/site-config.json`, `data/source-metadata.json`, `data/clause-summaries.json`, `data/content-ownership.json`, `scripts/sitemap.json`, `README.md`, and everything under `docs-for-maintainers/`. The PDF under `source/` is committed source too, but its bytes must never change. `data/etsi-content-hashes.json` is the one exception: it's committed, but it's only ever written by `scripts/update_etsi_hashes.py` (see "Reproduced ETSI wording integrity" below), never by hand.

**Generated — never hand-edit:** *everything* under `docs/`. Rendered pages (`docs/*.html`, including `docs/404.html` and the `docs/accessibility-statement.html` redirect stub), generated extras (`docs/search-index.json`, `docs/sitemap.xml`, `docs/robots.txt`, `docs/.nojekyll`), and the copies the build makes of the hand-authored sources (`docs/assets/` from `assets/`, `docs/source/` from `source/`, `docs/_headers` and `docs/_redirects` from `deployment/cloudflare/`). They are committed to the repository (GitHub Pages serves straight from `docs/` with no build step of its own), but they are output, not input. If you edit any file under `docs/` directly, the next `python3 scripts/build.py` run will silently overwrite your change — and separately, `git status --porcelain -- docs/` after a rebuild (exactly what CI checks) will show your manual edit as a difference the moment anyone rebuilds, so it can't quietly become the "real" version. `scripts/build.py` reads nothing under `docs/` at all: the assets it hashes for the cache-busting `?v=` URLs and the PDF whose size it computes are the source copies under `assets/` and `source/`.

The build has no dependencies beyond the Python 3 standard library (see `.python-version` for the interpreter line CI pins):

```
python3 scripts/build.py
```

This reads `data/site-config.json`, `data/source-metadata.json`, `scripts/sitemap.json`, `content/*.html`, `assets/`, `source/` and `deployment/cloudflare/`, validates them (see [Validation](#validation-the-build-fails-on-invalid-content) below), and regenerates `docs/` **atomically**: the whole site is generated into a temporary staging directory, the complete staged output is validated, and only then is `docs/` swapped for the staging tree (two same-filesystem renames). A failed build leaves the existing `docs/` untouched and removes the staging directory; a successful build removes stale generated files automatically, because nothing from the previous `docs/` survives the swap. **Re-run the build after editing any source above, and commit the resulting `docs/` changes — including deletions — together with your source edit.**

To verify a change is valid without writing `docs/`:

```
python3 scripts/build.py --check-only
```

To verify the committed `docs/` output actually matches a clean rebuild from source (this is exactly what CI checks on every push):

```
python3 scripts/build.py
git status --porcelain -- docs/    # must print nothing
```

If that reports changes, `docs/` was out of date with its sources — rebuild and commit the difference (`git diff --exit-code -- docs/` alone would miss newly generated files that were never committed, which is why CI uses `git status`). The build does not inject a live timestamp or any other run-to-run-varying value into generated pages, specifically so this comparison is meaningful: a clean rebuild from unchanged source always produces byte-identical output. Because `docs/` is replaced atomically, the check also catches stale files that should have been deleted, missing copied assets or deployment files, changed PDF bytes, and changed generated 404 output. [`.github/workflows/ci.yml`](.github/workflows/ci.yml) runs exactly this check on every push — it only ever fails the build if a difference is found, and never itself commits, amends, or overwrites `docs/` (no rebuild/commit loop).

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
- After adding or renumbering headings, run `python3 scripts/normalize_content.py` to bring every id in `content/` in line with the rule above in one pass (it also strips a leading fragment `<h1>`), then rebuild. `python3 scripts/normalize_content.py --check` reports what would change without writing anything (exit 0 only when everything is already normalised and valid). Duplicated clause numbers are an error, never silently suffixed: the tool reports both headings and writes nothing until the source numbering is corrected by hand.
- Every numbered heading (h2/h3/h4) automatically becomes its own permalink at build time: the heading's text is wrapped in a self-referencing link (one keyboard tab stop whose accessible name is the heading text itself — no separate "#" control), which navigates to the heading's anchor and, with JavaScript, also copies the deep link. You don't add this by hand in content fragments.
- Heading levels should not skip (an `<h3>` should not be followed directly by an `<h4>`'s child, i.e. by an `<h5>`, without an intervening `<h4>` on the way down). The build fails on a skipped level.
- A page with 2 or more h2/h3 headings automatically gets an "On this page" jump list at build time, generated from those headings — nothing to add by hand. Its depth is deliberately capped at h2/h3 (the same two levels the left-hand sidebar shows) — h4 requirement-level headings are excluded even on the longest pages, since listing every one of them (up to ~100+ on the biggest clauses) would make the list unusable rather than helpful. Website-only headings ("About this clause", "On this page" itself, etc.) are never included — `build_on_this_page()` only ever sees the fragment's own parsed ETSI headings, and this is re-checked on the final rendered output (see `on-this-page-utility-heading` in the validator).
- Every clause and annex page has a short "About this clause"/"About this annex" orientation box, kept in `data/clause-summaries.json` keyed by slug. Keep each to 1–2 short paragraphs, and describe what the clause covers without interpreting conformance requirements, adding obligations, or narrowing scope. The build automatically appends the fixed "reproduced from the ETSI draft, not simplified or changed" sentence; don't duplicate it in the JSON. To state that a part is normative or informative, set the optional `"nature": "normative"` / `"informative"` field — the build appends the standard "It is normative/informative, which means …" sentence from one place, so its wording can't drift between entries. You can also link the words "normative" or "informative" to their definition on the About page by writing `{{normative}}` / `{{informative}}` in free text.
- Cross-references in the reproduced text — "see clause 5.1.3", "clauses 9, 10 and 11", "Annex ZA", bibliography citations like "[i.25]" — are turned into links automatically at build time (`link_cross_references()` in `scripts/build.py`). This is markup only: no wording changes (the wording-integrity check would fail if it did), text already inside a link, heading, or table caption is never touched, and anything the build can't resolve to a certain target is left as plain text — e.g. "Annex I", which belongs to an EU Directive, not this document. Clause 2's bibliography entries get stable `ref-…` ids so citations can deep-link to them.
- The site search is entirely static: the build writes `docs/search-index.json` (one entry per heading section, glossary term, and page intro — deterministic, so reproducible builds still hold), and `assets/js/site.js` filters it in the browser on `search.html`. No search service, no third-party library. Nothing to maintain by hand — the index regenerates from content on every build.
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
- any structured JSON input (`data/*.json`, `scripts/sitemap.json`) that is malformed, contains a duplicate key, or has the wrong top-level type — for *optional* files (e.g. `data/content-ownership.json`) only a genuinely missing file is acceptable; an existing malformed file is always an error, never silently replaced with a fallback (see `scripts/json_data.py`);
- an invalid `data/site-config.json`: missing or unknown fields, a non-HTTPS or trailing-slash-less `baseUrl`, a query/fragment on the base URL, a malformed `repositoryUrl`, an unsafe `repositoryRef` (anything beyond letters, digits, dots, underscores, hyphens and internal slashes), or an unrecognised `deploymentTarget`;
- a missing or malformed `deployment/cloudflare/_headers`/`_redirects`, an active redirect rule with a non-rooted source, invalid target, or unsupported status, a duplicate redirect source, or a detectable redirect loop;
- a generated `docs/404.html` with the wrong number of `<h1>` elements, a missing `noindex`, a canonical URL, an automatic redirect, a missing Home/Search/first-clause link, or any relative link (the 404 page is served at arbitrary missing paths, so every link on it must be absolute);
- a staged copy of the source PDF or a deployment file that is not byte-identical to its committed source;
- more or fewer than exactly one non-empty `<h1>` on any generated page;
- a numbered heading whose id doesn't match its clause number;
- a heading (h2/h3) with no id at all;
- duplicate ids on the same page;
- a heading level that skips a level going deeper;
- malformed HTML (unclosed or mismatched tags);
- any internal `href`/`src`/`srcset` reference (collected with an HTML parser, so single-quoted and unquoted attributes and every srcset candidate are all seen) that resolves outside the published `docs/` tree, points at a file this build doesn't publish, or carries a `#fragment` with no matching id on the target page (same-page and cross-page alike; query strings are ignored and percent-encoding is decoded first) — plus any `javascript:` URL, which is rejected outright;
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

The site has light and dark themes:

- **Automatic vs explicit:** the OS preference applies automatically (`prefers-color-scheme`); Reading options offers Match device setting / Light / Dark. An explicit choice sets `data-theme` on `<html>` and always beats the OS setting.
- **Persistence and early application:** the choice is stored with the other reader preferences in `localStorage` and applied by a synchronous inline script deliberately placed before the stylesheet in the page head — which prevents (or at worst minimises) a wrong-theme flash, and also keeps the browser-chrome `theme-color` in step with the *resolved* theme. Unit tests assert the script's ordering and synchronous application statically; actual flash behaviour is still worth an occasional manual look in real browsers. Each preference is validated independently on load, so malformed or pre-dark-mode stored data never discards the others.
- **Without JavaScript** the OS preference still applies (the themes are pure CSS); only the explicit override needs script.
- **Print** always forces a black-on-white palette regardless of the screen theme, including table headers, callouts and companion guidance.
- **Token-level only:** the dark palette redefines the custom properties in `assets/css/style.css` (in two deliberately identical blocks — one for the media query, one for the explicit attribute), and fixed white-text surfaces (the blue title band, navigation highlights, buttons) keep their colours in both themes.
- **Verification in CI:** `scripts/check-contrast.py` parses both palettes straight from the CSS (so it cannot drift), fails if the two dark blocks differ, and checks its explicit list of colour pairings against WCAG 2.2 AA thresholds (4.5:1 text, 3:1 UI components) — the pairings the design actually produces, not every conceivable combination. The axe sweep (`npm run test:a11y`) checks every page in both automatic themes plus representative pages under both explicit overrides, and `npm run test:theme` covers persistence, pre-paint application, theme-color sync, print output and forced-colours mode. Real screen-reader and high-contrast-mode sessions remain manual checks (see `docs-for-maintainers/accessibility-testing.md`). This site is **designed and tested with the aim of meeting WCAG 2.2 Level AA** — that is a target, not an independently audited conformance certificate. See the [accessibility statement section of the About page](docs/about.html) (or `content/about.html` before building) for exactly what has been automated-tested, what still needs manual evaluation, and how to report a problem. Manual, non-automatable testing procedure and the test log live in [`docs-for-maintainers/accessibility-testing.md`](docs-for-maintainers/accessibility-testing.md).

## Testing

```
npm install
npx playwright install --with-deps chromium   # once, for the browser suites
npm run build          # python3 scripts/build.py
npm test               # THE complete supported suite (= test:ci = test:static + test:browser)
npm run test:static    # unit tests + theme contrast + build + html-validate (no network, no browser)
npm run test:unit      # python3 -m unittest scripts/test_build.py
npm run test:contrast  # python3 scripts/check-contrast.py
npm run test:html      # html-validate "docs/*.html"
npm run test:browser   # all four Playwright suites below (requires the Chromium install)
npm run test:a11y      # axe-core against every page in both themes, plus explicit-override runs
npm run test:layout    # responsive layout assertions at 320-1920px
npm run test:search    # site-search end-to-end checks
npm run test:theme     # theme behaviour: persistence, pre-paint ordering, theme-color sync, print palette, forced colours
```

`npm test` runs the complete supported suite — the same thing CI runs (`test:static` then `test:browser`). The browser suites need a Chromium binary; run `npx playwright install --with-deps chromium` once before the first local run. If you only want the fast, no-browser validation while iterating, use `npm run test:static`. Manual browser, screen-reader and Windows high-contrast checks are still required before claiming conformance — see `docs-for-maintainers/accessibility-testing.md`. The layout test checks, on representative pages at seven viewport widths (320-1920px): no page-level horizontal overflow, no sidebar/content overlap, the content column actually growing on wider screens, table wrappers only scrolling when the table's measured minimum width genuinely exceeds the space, and the mobile contents disclosure still working. See [`.github/workflows/ci.yml`](.github/workflows/ci.yml) for exactly what runs in CI and why these tools specifically — see the comment at the top of that file.

## Maintenance

Routine maintenance tasks — updating the ETSI publication status, the status-check date, the source PDF link, clause summaries, the wording-integrity baseline, running the full test suite, reviewing the accessibility statement, recording manual testing, and more — are documented in [`docs-for-maintainers/maintenance.md`](docs-for-maintainers/maintenance.md).

## Hosting

This site is published for free via GitHub Pages, serving from the `docs/` folder. Once this branch is merged to the default branch, enable it under **Settings → Pages → Source: Deploy from a branch → (default branch) /docs**.

The production base URL — used for canonical URLs, Open Graph tags, `sitemap.xml` and `robots.txt` — comes from `data/site-config.json`, and nowhere else. Changing the domain means updating that file, rebuilding, committing the regenerated `docs/`, and re-running the tests.

The repository is also **prepared** for a later Cloudflare Pages deployment (`deployment/cloudflare/_headers` and `_redirects` are published as `docs/_headers` and `docs/_redirects`, which GitHub Pages ignores), but **Cloudflare deployment is not active** and the canonical production domain remains GitHub Pages until a real custom domain is deliberately selected and configured. See [`docs-for-maintainers/cloudflare-pages.md`](docs-for-maintainers/cloudflare-pages.md).

## Licensing, copyright and publication readiness

**This section states facts and open questions. It does not make a legal determination, and nothing below should be read as one.**

### ETSI reproduction permission

The source PDF's own front matter (reproduced in full on the [About page](content/about.html)) states that reproduction requires ETSI's written permission. **Permission to reproduce and publish the ETSI material has not yet been obtained.** Until written permission from ETSI has been received and its scope and conditions have been recorded in [`LICENSES.md`](LICENSES.md), this project must not be treated as cleared for public publication or redistribution of the ETSI material — that includes the reproduced HTML standard, the committed source PDF, the ETSI excerpts in the search index, and public availability of all of these through a cloneable GitHub repository. When permission is obtained, record it in the ETSI permission record in `LICENSES.md` from the actual correspondence only.

### Licence

The original software used to build and operate this website is licensed under the [MIT License](LICENSE).

Original website-authored documentation and design material are licensed under the [Creative Commons Attribution 4.0 International Licence](LICENSE-CONTENT.md) (CC BY 4.0).

These licences do not apply to the reproduced ETSI standard, the ETSI source PDF, ETSI legal notices, trademarks, fonts or other third-party material. Permission to reproduce and publish the ETSI material has not yet been obtained (see above), and the open licences on the surrounding website must never be read as a licence to reproduce, publish or redistribute the ETSI material itself.

See [`LICENSES.md`](LICENSES.md) for the detailed scope, exclusions, the ETSI permission record, and attribution requirements.

### Trademarks

The source document's own front matter — reproduced verbatim on the [About page](content/about.html#trademarks) — states that it may include trademarks and tradenames asserted or registered by their owners, that ETSI claims no ownership of these except where indicated, and that reproducing the document does not convey any right to use or reproduce those trademarks. That notice, and the specific trademark names it lists (DECT, PLUGTESTS, UMTS, 3GPP, LTE, 5G, oneM2M, GSM, BLUETOOTH, and others named there), must not be edited, summarised, or removed. Nothing in this repository's own code/design licence extends any right to use those names or logos.

### Font licences

The self-hosted webfonts under `assets/fonts/` — Overpass and Source Sans 3, both distributed by Google Fonts, published as copies under `docs/assets/fonts/` — are released under the [SIL Open Font License 1.1](https://openfontlicense.org/), which permits embedding and redistribution, including in a project with different licensing terms for its other components. No separate action is required for these two fonts, but re-verify the licence of any font added later.

### Publication-readiness checklist

Do not treat this site as ready for public release until every item below is either checked or explicitly waived by whoever is accountable for that decision.

- [ ] **Written permission from ETSI to reproduce and publish the standard has been obtained.** *(Required — this remains a publication blocker; every other item on this list only matters once this one is genuinely true.)*
- [ ] The permission reference, grantor, date, scope, permitted publication channels and applicable conditions have been recorded in [`LICENSES.md`](LICENSES.md) from the actual correspondence.
- [ ] Permission to host and distribute the ETSI source PDF has been specifically confirmed.
- [ ] Permission for ETSI material to remain in a publicly cloneable and forkable repository has been specifically confirmed.
- [x] A licence has been chosen and recorded for this site's own code/design (MIT for software, CC BY 4.0 for original design/documentation — see `LICENSE`, `LICENSE-CONTENT.md`, `LICENSES.md`), and each statement of it is explicit that it does not extend to the reproduced ETSI text or to the trademarks named in it. *(The `LICENSE` file's `[COPYRIGHT HOLDER]` placeholder still needs the legal copyright holder's name.)*
- [ ] `npm test` (the complete suite: static checks plus all four Playwright browser suites) passes on the commit being published.
- [ ] `python3 scripts/build.py` then `git status --porcelain -- docs/` prints nothing (committed `docs/` matches a fresh rebuild, with no stale or missing files).
- [x] The accessibility statement has a real reporting route (currently a GitHub issues link — replace with a dedicated contact address if/when one exists).
- [ ] The accessibility statement's "Review history" section has at least one real, completed review recorded.
- [ ] A genuine manual accessibility test pass has been completed against `docs-for-maintainers/accessibility-testing.md`, and its log updated.
- [ ] `data/source-metadata.json`'s checksum has been re-verified against the currently committed source PDF.
