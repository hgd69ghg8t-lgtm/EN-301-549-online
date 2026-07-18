# Session handover — 404 regression fix and runtime validation (18 July 2026)

Base commit before this work: `a6ce872` (merge of PR #12, the
generated-output separation). This session's commit SHA is recorded at
the top of the commit itself; run `git log -1` on the
`claude/en301549-followup-fixes-fgz3xd` branch to read it.

Follow-up fixes only. **The deferred performance-optimisation phase was
NOT started** (no webfont removal, JS splitting, search redesign, Web
Worker, fingerprinted filenames, immutable caching, CSP, Cloudflare
deploy/reconfigure, canonical-domain change, or ETSI-wording change).

## What was done

### 1. 404 page: data-action corruption fixed (the urgent regression)

The generated `docs/404.html` had corrupted page-tools markup:
`data-action="print"` and `data-action="copy-link"` had been rewritten
to absolute URLs (`data-action="https://…/print"`), because
`absolutise_local_links()` used a regex that matched the `action`
substring inside `data-action`. `site.js` binds to the exact values
`[data-action='print']` and `[data-action='copy-link']`, so Print and
Copy-link silently did nothing on the 404 page.

Fix: `absolutise_local_links()` is now HTMLParser-based
(`_LocalLinkFinder`). It rewrites **only** real URL attributes — `href`
and `src` on any element, and `action` on a `<form>` — and only
reconstructs tags that actually carry one; every other tag, attribute
(`data-*`, `aria-*`, anything merely ending in `action`/`href`/`src`)
and text node passes through byte-identical. Values are entity-decoded
by the parser and re-escaped exactly once (shared `escape_attr()`),
attribute order and boolean attributes preserved, and absolute /
`mailto:` / `tel:` / `data:` / scheme-relative / fragment-only URLs are
left untouched. A build-time guard in `validate_not_found_page()`
(`404-data-action-rewritten`) fails the build if either data-action ever
loses its exact value again.

### 2. Tests added for the 404 page

- **Unit** (`scripts/test_build.py`): `AbsolutiseLocalLinksTests` (16
  cases: href/src/form-action absolutised; data-action/data-href/
  data-src/aria-* untouched; action outside a form untouched; absolute
  and special-scheme URLs, fragment-only links, query+fragment
  preservation, attribute order, boolean attrs, escape-exactly-once,
  byte-identical pass-through of SVG/self-closing tags, malformed HTML,
  and the rendered-page assertions), plus new cases in `NotFoundPageTests`
  and `ResourceCollectorTests`.
- **Browser** (`scripts/test-404.mjs`, new suite, wired as
  `npm run test:404` and into `test:browser`): direct visit to
  `/404.html` **and** two real missing URLs (`/this-page-does-not-exist`
  and a nested `/nested/path/that-does-not-exist`), served by the test
  server with a real 404 status like static hosting. Asserts no runtime
  errors, exactly one visible `<h1>`, noindex, no canonical, no
  auto-redirect, CSS/JS/fonts/icons load, the exact `data-action` values
  survive, clicking Print reaches `window.print()`, clicking Copy writes
  the address to the clipboard and announces in the live region, the
  Home/Search/Clause 1 links are absolute and Home navigates, and
  keyboard access reaches the main nav and every Page-tools control.
- **axe** (`scripts/test-a11y.mjs`): the 404 page is now swept in light
  and dark modes (it is deliberately absent from the sitemap, so the
  sitemap sweeps never saw it).

### 3. Runtime error + resource-request enforcement (defence in depth)

- New shared infra `scripts/browser-test-lib.mjs`: one static server
  (now serving the custom 404 page with a 404 status), one Chromium
  launcher, and `trackRuntimeIssues()` — every browser suite now fails
  on an unexpected `pageerror` (covers unhandled promise rejections too),
  `console` error, failed same-origin request, or same-origin response
  with status ≥ 400. Narrow, documented exceptions only (the deliberate
  404-navigation console message where a 404 status is the behaviour
  under test, and browser-generated `net::ERR_ABORTED` navigation
  aborts). No global console-error suppression.
- All five suites (a11y, layout, search, theme, 404) refactored onto the
  shared infra and call `reportRuntimeIssues()` at the end.

### 4. CSS `url(...)` dependency validation (build-time)

- New `validate_css_resources()` runs against the staged tree: every
  local `url(...)` in every published stylesheet must resolve to a
  published file without escaping the output tree. Quoted/unquoted URLs,
  `../`, query strings, fragments, `data:` and external `https:` all
  supported; tree-escape and root-absolute paths rejected. Both
  self-hosted fonts are covered — a unit test deletes each in turn and
  confirms the build fails, and the browser request-failure enforcement
  catches a missing font as a second line of defence.

### 5. Site-configuration consistency + escaping

- **siteName is now the source of truth.** `build_wordmark()` generates
  the visible header wordmark from `siteName`; the existing two-tone
  "Accessible**Docs**" treatment is preserved by one narrow validated
  rule (a CamelCase pair gets the accent on the second word), and any
  other name renders as ordinary escaped text — no assumption that every
  future name splits. `og:site_name` now carries the configured name.
- All configuration values (`siteName`, `documentLabel`) are
  context-escaped everywhere they are emitted (wordmark, visually hidden
  text, page title, OG tags, the accessibility-statement stub). Tests
  cover `& < > " '` and Unicode with no double-escaping and no injection.

### 6. Repository-document links generated from config (branch-rename safe)

- New validated `repositoryRef` field in `data/site-config.json` (safe
  branch-name chars only — no query/fragment/`..`/dot-leading segments).
  `repository_document_url()` builds GitHub blob URLs from
  `repositoryUrl` + `repositoryRef`; `content/about.html` now uses a
  `{{ACCESSIBILITY_TESTING_URL}}` token instead of three hardcoded
  `/blob/claude/pdf-accessible-website-j88o8l/` links. A test proves a
  branch rename changes every generated documentation link at once.

### 7. Atomic-backup cleanup made transparent

- `replace_docs_dir()`: once the new `docs/` is installed the
  publication has succeeded, so a failure to delete the `.docs-old-*`
  backup is now a **warning** (naming the leftover path and an `rm -rf`
  instruction), not a build failure. Stale backups from earlier runs are
  retried on later builds. The live `docs/` is never at risk. Three unit
  tests simulate cleanup failure.

### 8. Missing-resource guidance points at source, not docs/

- `missing_resource_fix()` now directs maintainers to `assets/`,
  `source/`, `deployment/cloudflare/`, or the build code as appropriate,
  and always says **not** to hand-edit `docs/` (generated output,
  replaced wholesale each build).

### 9. Documentation corrections

- `assets/css/style.css`: font comment now says source lives in
  `assets/fonts/`, copied to `docs/assets/fonts/`.
- `deployment/cloudflare/_redirects`: `parse_redirects()` →
  `validate_redirects()`.
- `docs-for-maintainers/cloudflare-pages.md` + `README.md`: no longer
  claim "no Cloudflare deployment exists"; state factually that a
  Cloudflare Git integration has **attempted and failed** a deployment
  and the site is not confirmed as deployed.

### 10. Cloudflare failure recorded (not resolved)

- `cloudflare-pages.md` has a new "Observed deployment failure (18 July
  2026)" section: the failed check on PR #12 was named "Workers Builds:
  accessibledocs" and presented as a Cloudflare **Workers** build (not
  Pages), failed on commit `8f25d253`, and its build log is only in the
  Cloudflare dashboard (not accessible here). A troubleshooting
  checklist covers confirming Pages-not-Workers, framework preset None,
  blank root directory, build command `python3 scripts/build.py`, output
  directory `docs`, production branch, and reading the dashboard log. The
  exact cause is **not guessed at**. No Cloudflare settings, DNS, custom
  domain or public-availability changes were made.

## Release / permission constraint (unchanged)

The About page's warning that written ETSI permission has **not** been
obtained is untouched. Nothing here presents the site as cleared for
public publication, changes the deployment target, or alters ETSI
licensing text or the canonical production domain.

## Integrity

- **No reproduced ETSI wording changed** — `git diff --word-diff` over
  `content/clause-*` / `content/annex-*` is empty; content-page diffs are
  limited to `og:site_name` and the CSS `?v=` hash in the head.
- **`data/etsi-content-hashes.json` unchanged.**
- **Source PDF bytes/checksum unchanged** — SHA-256
  `c2247f2d59c6f1465e5c10a8d6720aaa79c2d82a420435eb8f487e34dcc0672a`
  (matches `data/source-metadata.json`).
- Committed `docs/` matches a clean rebuild.

## Tests run (all passing)

`python3 -m unittest scripts/test_build.py` (144), `check-contrast.py`
(80 pairings), `npm run build`, `npx html-validate "docs/*.html"`,
`npm run test:a11y` / `test:layout` / `test:search` / `test:theme` /
`test:404`, full `npm test`, `normalize_content.py --check`, and the
etsi-hash / word-diff integrity checks.

## Remaining work (future sessions)

- The deferred performance phase: JS splitting, webfont strategy,
  minification, Web Workers, search-relevance tuning — none started.
- Fingerprinted asset filenames + immutable caching; a tested CSP.
- The actual Cloudflare Pages deployment (still unverified; canonical
  domain remains GitHub Pages).
