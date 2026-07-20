# Building, testing and hosting

How the repository is laid out, how the build turns source into the
published `docs/`, how it validates itself, and how it's hosted. For the
rules about editing content, see
[`content-authoring.md`](content-authoring.md); for licensing and
publication readiness, see [`../LICENSES.md`](../LICENSES.md).

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
                     verbatim from the ETSI draft. See content-authoring.md
                     for the rule about never editing the latter.
assets/             Hand-authored static assets: assets/css/style.css and
                     the assets/js/ feature modules, plus the
                     favicons/logo under assets/img/. The build minifies
                     and content-hashes the CSS/JS into docs/assets/ under
                     fingerprinted filenames; images are copied as-is.
                     Typography uses system fonts, so no webfonts are
                     stored or published.
source/             The original ETSI source PDF (the source copy). The
                     build copies it into docs/source/, so the PDF stays
                     published at its existing URL. Never edit its bytes.
deployment/
  cloudflare/        Cloudflare Pages configuration source (_headers,
                     _redirects), copied by the build to docs/_headers
                     and docs/_redirects. Prepared for a possible later
                     Cloudflare Pages deployment; GitHub Pages ignores
                     these files. See cloudflare-pages.md.
data/
  site-config.json   The site's identity and deployment configuration:
                     site name, document label, the production base URL,
                     the repository URL, the repository ref (default
                     branch), and the deployment target. Strictly
                     validated at build time.
  source-metadata.json  Machine-readable source/version metadata,
                     rendered onto the About page at build time.
  clause-summaries.json  The website-authored "About this clause/annex"
                     orientation text, keyed by slug.
scripts/
  build.py           The build script and validator.
  minify.py          Deterministic CSS/JS minifiers (standard library).
  heading_parser.py  Shared stdlib HTML heading parser.
  normalize_content.py  Rewrites content/ ids from clause numbers.
  sitemap.json        Single source of truth for the site's pages.
docs/                Generated output, served by GitHub Pages. ENTIRELY
                     generated — never hand-edit; re-run the build.
docs-for-maintainers/  This documentation.
.github/workflows/   CI: build, validate and test every push and PR.
```

## Which files are source of truth, and how to rebuild

**Hand-edit:** everything under `content/`, `assets/`, `deployment/cloudflare/`, `data/site-config.json`, `data/source-metadata.json`, `data/clause-summaries.json`, `data/content-ownership.json`, `scripts/sitemap.json`, `README.md`, and everything under `docs-for-maintainers/`. The PDF under `source/` is committed source too, but its bytes must never change. `data/etsi-content-hashes.json` is the one exception: it's committed, but it's only ever written by `scripts/update_etsi_hashes.py`, never by hand.

**Generated — never hand-edit:** *everything* under `docs/`. Rendered pages (`docs/*.html`, including `docs/404.html` and the `docs/accessibility-statement.html` redirect stub), generated extras (`docs/search-index.json`, `docs/search-suggestions.json`, `docs/sitemap.xml`, `docs/robots.txt`, `docs/.nojekyll`), the minified, content-fingerprinted CSS/JS produced from `assets/` (`docs/assets/css/style.<hash>.css`, `docs/assets/js/main.<hash>.js`, …), and the verbatim copies of the other sources (`docs/assets/img/`, `docs/source/`, `docs/_headers`, `docs/_redirects`). They are committed (GitHub Pages serves straight from `docs/`), but they are output, not input: editing any file under `docs/` directly is overwritten by the next build, and `git status --porcelain -- docs/` after a rebuild (what CI checks) shows the edit as drift.

The build has no dependencies beyond the Python 3 standard library (see `.python-version` for the interpreter CI pins):

```
python3 scripts/build.py
```

This reads `data/`, `scripts/sitemap.json`, `content/*.html`, `assets/`, `source/` and `deployment/cloudflare/`, validates them (see [Validation in content-authoring.md](content-authoring.md#validation-the-build-fails-on-invalid-content)), and regenerates `docs/` **atomically**: the whole site is generated into a temporary staging directory, the complete staged output is validated, and only then is `docs/` swapped for the staging tree (two same-filesystem renames). A failed build leaves `docs/` untouched; a successful build removes stale generated files automatically. **Re-run the build after editing any source, and commit the resulting `docs/` changes — including deletions — with your source edit.**

Check a change without writing `docs/`:

```
python3 scripts/build.py --check-only
```

Verify committed `docs/` matches a clean rebuild (what CI checks on every push):

```
python3 scripts/build.py
git status --porcelain -- docs/    # must print nothing
```

The build injects no live timestamp or other run-to-run-varying value, so a clean rebuild from unchanged source always produces byte-identical output. Because `docs/` is replaced atomically, the check also catches stale files that should have been deleted, missing copied assets, changed PDF bytes, and changed generated 404 output.

### Reproduced ETSI wording integrity

`data/etsi-content-hashes.json` records a hash of the reproduced text in every clause/annex `content/*.html` file (every sitemap page except the website-authored `index`/`about`/`search`). The build recomputes and compares these hashes on every run, so an accidental change to reproduced ETSI wording fails the build and names the exact file affected. The hash is computed over text content only, with markup stripped and whitespace collapsed first — so a purely structural edit (heading level, id, class, reindentation) never trips it; only a change to the actual reproduced words does.

The baseline is never updated automatically. If you have a genuine reason to change it — most likely, correcting an actual transcription error against the source PDF — run:

```
python3 scripts/update_etsi_hashes.py
```

and explain what you changed and why in your commit message. Do not run this just to make a validation failure go away without first checking why the wording changed.

To extract new content from the source PDF, you'll also need [`pdftotext`](https://poppler.freedesktop.org/) (from `poppler-utils` — `apt-get install poppler-utils` / `brew install poppler`).

## Accessibility

The site is designed and tested with the aim of meeting WCAG 2.2 Level AA — a target, not an independently audited conformance certificate. It has light and dark themes:

- **Automatic vs explicit:** the OS preference applies automatically (`prefers-color-scheme`); Reading options offers Match device setting / Light / Dark. An explicit choice sets `data-theme` on `<html>` and beats the OS setting.
- **Persistence and early application:** the choice is stored in `localStorage` and applied by a synchronous inline script placed before the stylesheet in the head, preventing (or minimising) a wrong-theme flash and keeping the browser-chrome `theme-color` in step with the resolved theme.
- **Without JavaScript** the OS preference still applies (the themes are pure CSS); only the explicit override needs script.
- **Print** always forces a black-on-white palette regardless of the screen theme.
- **Verification in CI:** `scripts/check-contrast.py` parses both palettes straight from the CSS and checks its colour pairings against WCAG 2.2 AA thresholds; `npm run test:a11y` runs axe-core over every page in both automatic themes plus explicit overrides and the 404 page; `npm run test:theme` covers persistence, pre-paint ordering, theme-color sync, print output and forced-colours mode. Real screen-reader and high-contrast sessions remain manual (see [`accessibility-testing.md`](accessibility-testing.md)).

The [accessibility statement on the About page](../content/about.html) records exactly what has been automated-tested, what still needs manual evaluation, and how to report a problem.

## Testing

```
npm install
npx playwright install --with-deps chromium   # once, for the browser suites
npm run build          # python3 scripts/build.py
npm test               # THE complete supported suite (= test:static + test:browser)
npm run test:static    # unit tests + theme contrast + build + html-validate (no browser)
npm run test:unit      # python3 -m unittest scripts/test_build.py
npm run test:contrast  # python3 scripts/check-contrast.py
npm run test:html      # html-validate "docs/*.html"
npm run test:browser   # the Playwright suites below (requires the Chromium install)
npm run test:a11y      # axe-core: every page in both themes, explicit overrides, the 404 page
npm run test:layout    # responsive layout assertions at 320-1920px
npm run test:search    # site-search end-to-end checks
npm run test:theme     # theme behaviour: persistence, pre-paint, theme-color sync, print, forced colours
npm run test:404       # the generated 404 page (direct visit + real missing URLs)
npm run test:performance  # deterministic resource-count/size budgets (see performance.md)
```

`npm test` is the same thing CI runs. The browser suites need a Chromium binary. `npm run test:static` is the fast, no-browser subset for quick iteration. `npm run test:performance` enforces deterministic front-end budgets (resource counts and byte sizes, never wall-clock) — see [`performance.md`](performance.md). Manual browser, screen-reader and Windows high-contrast checks are still required before claiming conformance — see [`accessibility-testing.md`](accessibility-testing.md). [`.github/workflows/ci.yml`](../.github/workflows/ci.yml) documents exactly what runs in CI and why.

## Hosting

Published for free via GitHub Pages, serving from the `docs/` folder. Once this branch is merged to the default branch, enable it under **Settings → Pages → Source: Deploy from a branch → (default branch) /docs**.

The production base URL — used for canonical URLs, Open Graph tags, `sitemap.xml` and `robots.txt` — comes from `data/site-config.json`, and nowhere else. Changing the domain means updating that file, rebuilding, committing the regenerated `docs/`, and re-running the tests.

The repository is also **prepared** for a later Cloudflare Pages deployment, but **Cloudflare deployment is not active** and the canonical production domain remains GitHub Pages until a real custom domain is deliberately selected and configured. See [`cloudflare-pages.md`](cloudflare-pages.md).
