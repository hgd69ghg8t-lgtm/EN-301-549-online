# Session handover — generated-output separation and deployment preparation (17 July 2026)

Main commit: `3238e3341` (short: `3238e33`)
("Separate generated output and prepare static deployment")

Previous session's handover (build-tooling hardening, commit `dde6f19`)
is superseded by this file; its work is untouched.

## What was done

Four infrastructure changes; no content, design, search-relevance or
performance work. The performance-optimisation phase (JS splitting,
webfont removal, minification, Web Workers) has NOT been started.

### 1. Source assets separated from generated docs/ + atomic build

- `docs/` is now **entirely generated**. Hand-authored sources moved out:
  - `assets/` — css/style.css, js/site.js, img/ (favicons + logo),
    fonts/ (moved from `docs/assets/`, bytes unchanged except the
    fonts/README.md licence-link path).
  - `source/en_301549v040100va.pdf` — now the real file (the old layout
    kept the bytes in `docs/source/` with a top-level symlink; the
    direction is inverted). SHA-256 verified identical before and after:
    `c2247f2d59c6f1465e5c10a8d6720aaa79c2d82a420435eb8f487e34dcc0672a`
    (matches `data/source-metadata.json`).
  - `deployment/cloudflare/` — `_headers`, `_redirects`.
  The build copies all three back into `docs/` (`docs/assets/`,
  `docs/source/`, `docs/_headers`, `docs/_redirects`), so **every public
  URL is unchanged**, including `source/en_301549v040100va.pdf`.
- Atomic build (`publish_output()` in `scripts/build.py`): the whole
  site is generated into a `.docs-staging-*` temp dir inside the repo
  (same filesystem), the complete staged tree is validated
  (`validate_output_tree()`: site resources, deployment-file byte
  equality, redirects rules, 404 checks, PDF byte equality), and docs/
  is replaced by two `os.rename` calls (`replace_docs_dir()`). Any
  failure leaves the existing docs/ untouched and the `finally` block
  removes staging — no partial output can remain. Stale generated files
  disappear automatically because nothing from the old docs/ survives
  the swap. `docs/.nojekyll` is now generated (needed so GitHub Pages
  serves the underscore files).
- `--check-only` stages and validates fully, then discards staging.

### 2. Validated site configuration (`data/site-config.json`)

- Fields: `siteName`, `documentLabel`, `baseUrl`, `repositoryUrl`,
  `deploymentTarget` (allowed: `github-pages`, `cloudflare-pages`).
  Current values are the existing GitHub Pages ones — no custom domain
  invented; `deploymentTarget` is `github-pages`.
- Validation (`validate_site_config()`): unknown fields rejected, all
  fields required non-empty strings, baseUrl HTTPS + real hostname +
  trailing slash + no query/fragment, repositoryUrl HTTPS, target from
  the allowed list. Duplicate keys rejected by the shared loader.
- Single source for: canonical URLs, OG tags + social image, sitemap.xml,
  robots.txt, the 404 page's absolute links, and the visible repository
  links (new `{{REPOSITORY_URL}}` token used in `content/about.html`).
  The old `SITE_BASE_URL`/`DOC_LABEL` constants in build.py are now
  derived from the config. No environment-variable or CLI override was
  added (deliberately — reproducibility; no demonstrated need).

### 3. Cloudflare Pages preparation (NOT an active deployment)

- `deployment/cloudflare/_headers` → `docs/_headers`: X-Frame-Options
  DENY, X-Content-Type-Options nosniff, Referrer-Policy
  strict-origin-when-cross-origin, restrictive Permissions-Policy.
  **No CSP** (must first be designed/tested against the inline pre-paint
  theme script — no 'unsafe-inline' shortcuts) and **no immutable
  caching** (filenames aren't fingerprinted; only `?v=` changes) — both
  deferrals documented in the file and in cloudflare-pages.md.
- `deployment/cloudflare/_redirects` → `docs/_redirects`: comments only,
  no active rules (no legacy URLs exist; none invented). Active rules
  are validated at build time (`validate_redirects()`): rooted source,
  local-or-HTTPS target, status 301/302/303/307/308, duplicate sources
  rejected, loops detected.
- Generated accessible `docs/404.html`: shared template, exactly one
  `<h1>`, neutral "could not be found" wording, links to Home / Search /
  Clause 1, noindex, **no canonical**, no auto-redirect, works without
  JavaScript, **all links absolute** (404s serve at arbitrary depths on
  GitHub Pages/Cloudflare) — enforced by `validate_not_found_page()`.
  Excluded from sitemap.xml and navigation.
- `docs-for-maintainers/cloudflare-pages.md`: Git-integration setup
  (preset None, build `python3 scripts/build.py`, output `docs`,
  production branch), previews, custom-domain process (update
  site-config → rebuild → verify canonicals/sitemap), pages.dev
  duplicate-host handling, rollback, post-deploy verification. States
  clearly the canonical domain remains GitHub Pages.

### 4. Strict, consistent JSON loading (`scripts/json_data.py`)

- `load_json_data(path, rel, required=, expect_type=)` used by every
  loader: source-metadata (now also rejects unknown fields; optional
  fields explicit), site-config, clause-summaries, companion-guidance,
  content-ownership (previously swallowed malformed files → now a hard
  error), etsi-content-hashes (malformed/duplicate now distinct hard
  errors, missing keeps its tailored message), scripts/sitemap.json
  (strict, expects an array).
- Rules: required missing / malformed / duplicate key / wrong top-level
  type are always errors; optional files may only be *missing*. Errors
  carry file path, rule name, syntax line+column, duplicated key name,
  or expected type, and are deterministic. No JSON Schema dependency.

### 5. Test commands + CI

- package.json: `test:unit`, `test:contrast`, `test:html`,
  `test:static` (unit+contrast+build+html), `test:browser` (a11y,
  layout, search, theme), `test:ci` = static+browser, **`npm test` =
  `test:ci`** — the complete supported suite.
- CI (`.github/workflows/ci.yml`): calls the named npm scripts,
  `actions/setup-python@v5` pinned to 3.11 (matching new
  `.python-version`), workflow/ref concurrency with cancel-in-progress,
  `timeout-minutes: 30`, and the docs-cleanliness check now uses
  `git status --porcelain -- docs/` (catches stale deletions AND
  untracked generated files, which `git diff` alone misses).

## Files changed (34)

New: `data/site-config.json`, `scripts/json_data.py`,
`deployment/cloudflare/{_headers,_redirects}`, `assets/**` (moved),
`docs-for-maintainers/cloudflare-pages.md`, `.python-version`,
`docs/{404.html,_headers,_redirects}`.
Modified: `scripts/build.py` (config, strict loaders, template
placeholders for robots/canonical/social meta, 404 renderer, redirects
validator, staging/atomic publish), `scripts/{test_build.py,
check-contrast.py}`, `package.json`, `.github/workflows/ci.yml`,
`.gitignore` (`.docs-staging-*/`, `.docs-old-*/`), `README.md`,
`docs-for-maintainers/maintenance.md`, `content/about.html`
(`{{REPOSITORY_URL}}` token + one asset-path mention — website-authored
text only), `LICENSES.md`, `source/README.md`,
`source/en_301549v040100va.pdf` (symlink → real file, bytes identical).

## Tests run (all passing)

- `python3 -m unittest scripts/test_build.py` — 97 tests OK (48 new:
  JSON loader, site config, redirects, atomic build, 404)
- `python3 scripts/check-contrast.py` — 80 pairings OK
- `npm run build` — 37 pages; pre-existing pages byte-identical
- `npx html-validate "docs/*.html"` (incl. 404.html) — OK
- `npm run test:a11y` / `test:layout` / `test:search` / `test:theme` — OK
- `npm test` (full new suite) — OK
- `git status --porcelain -- docs/` after rebuild — no unstaged drift
- `git diff --exit-code HEAD -- data/etsi-content-hashes.json` — clean
- `git diff --word-diff=porcelain HEAD -- content/clause-*.html
  content/annex-*.html` — no output

(Local browser runs used the environment's pre-installed Chromium via
the scripts' existing `PLAYWRIGHT_CHROMIUM_PATH` escape hatch; CI still
installs Chromium through Playwright normally.)

## Integrity

- **No reproduced ETSI wording changed** (zero diffs under
  `content/clause-*` / `content/annex-*`).
- **`data/etsi-content-hashes.json` unchanged.**
- **Source PDF bytes identical** before/after the move — SHA-256
  `c2247f2d59c6f1465e5c10a8d6720aaa79c2d82a420435eb8f487e34dcc0672a`
  in `source/`, in the published `docs/source/` copy, and in
  `data/source-metadata.json`.
- Committed `docs/` matches a clean rebuild.

## Remaining work (future sessions)

- The deferred performance phase: JS splitting, webfont strategy,
  minification, Web Workers, search-relevance tuning — none started.
- Fingerprinted asset filenames (prerequisite for immutable caching in
  `_headers`), and a properly tested CSP.
- Cloudflare Pages deployment itself (prepared only; canonical domain is
  still GitHub Pages; no custom domain exists).
- External-link checking, URLs inside CSS/JS, and the normaliser's
  `--check` CI step — unchanged from the previous handover.
