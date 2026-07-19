# Session handover — static asset & search performance (19 July 2026)

Base commit before this work: `c58dcf0` (the 404-regression / runtime-
validation follow-up). This session's commit SHA: run `git log -1` on the
`claude/en301549-followup-fixes-fgz3xd` branch.

This is the **performance phase**. No content, wording, licensing or
deployment-status change. CSP, service worker, custom domain and any
Cloudflare account/deploy change are explicitly **not** started.

## Baseline (before) → outcome (after)

Full method, figures and limitations are in
[`performance.md`](performance.md). Headline per-page transfer (gzip on
disk, the production proxy) and requests excluding HTML:

| Page | Requests | Total transfer (gzip) |
|---|---|---|
| index.html | 5 → 3 | 94.2 KB → **16.0 KB** (−83%) |
| about.html | 5 → 4 | 101.7 KB → **24.1 KB** (−76%) |
| clause-9-web.html | 5 → 4 | 100.7 KB → **23.0 KB** (−77%) |
| annex-b-…relationship.html | 5 → 4 | 99.6 KB → **22.0 KB** (−78%) |
| search.html | 6 → 5 | 223.7 KB → **128.4 KB** (−43%) |
| 404.html | 6 → 4 | 89.5 KB → **11.2 KB** (−87%) |

- Header-search typing: fetched the **737 KB / 130 KB** full index →
  now the **128.8 KB / 16.4 KB** suggestion index (−87% transfer).
- Fonts: **66.5 KB / 2 requests on every page → 0**.

## What changed

### Fonts (Phase 2)
Removed both self-hosted webfonts and all `@font-face`. `--font-heading`
and `--font-body` now resolve to one system-font stack (`-apple-system,
BlinkMacSystemFont, "Segoe UI", Roboto, …`). Deleted `assets/fonts/`
(files + README); updated `LICENSES.md` and `README.md` (no font-licence
obligation now). Hierarchy comes from weight/size, unchanged. A pager
`min-width: 0` + `overflow-wrap` fix keeps the prev/next links from
overflowing at 320px under any font.

### JavaScript modules (Phase 3)
`assets/js/site.js` split into readable modules: `core`, `search-core`,
`preferences`, `navigation`, `page-tools`, `search-suggestions`,
`highlighting`, `tables`, `search-page`. They share a tiny
`window.__site` namespace (`announce`, `search.*`). The build
(`JS_BUNDLES`) composes them into published bundles:
- **main** (core+search-core+preferences+navigation+page-tools+
  search-suggestions+highlighting) — every page;
- **tables** — only pages with a `.table-wrap`;
- **search-page** — only `search.html`.
All `<script defer>` in `<head>`; the inline pre-paint theme script stays
synchronous. No framework, no bundler.

### Search indexes (Phase 4)
Two indexes: full-text `search-index.json` (bodies; `search.html` only)
and body-free `search-suggestions.json` (titles/URLs; header box). The
shared loader (`__site.search.makeIndexLoader`) checks `response.ok`,
content-type, array shape and required fields, surfaces failures
accessibly, and clears a rejected promise so a later attempt retries; the
header form still submits normally if suggestions fail. Full-index body
cap 4000→1500 (−12% raw; measured: top results for the representative
queries unchanged).

### Minification (Phase 5)
`scripts/minify.py` — conservative, deterministic, standard-library only
(no Node step in the build). Tokeniser-based: preserves strings, template
literals, regex literals, `url()` and `/*! */` licence comments; only
collapses whitespace (newline-preserving for JS → ASI-safe). CSS ~38%,
JS ~36% smaller before gzip. The browser suites run the minified output.

### Fingerprinting + caching (Phase 6)
`compute_assets()` minifies then content-hashes CSS/JS into
`assets/css/style.<hash>.css`, `assets/js/<bundle>.<hash>.js` (no `?v=`).
Hash changes iff bytes change; stale hashed files vanish on the atomic
rebuild; every generated reference (pages + absolute 404 URLs) is
validated. Images/PDF/HTML/sitemap/robots are **not** fingerprinted.
`deployment/cloudflare/_headers` now caches `/assets/css/*` and
`/assets/js/*` as `immutable, max-age=31536000`; HTML revalidates; search
indexes `max-age=3600`; images `max-age=86400`. GitHub Pages ignores
`_headers`.

### Performance budgets (Phase 7)
`scripts/test-performance.mjs` (`npm run test:performance`, in
`test:browser`/`test:ci`): deterministic request-graph and byte-size
budgets only — never wall-clock. Homepage ≤5 / clause ≤6 requests, zero
fonts, `main` ≤24 KB, suggestion index ≤160 KB, full index ≤660 KB, and
conditional bundles never loading on the wrong pages.
`scripts/measure-performance.mjs` produces the before/after report.

## Tests
`unittest` (all pass, incl. new Minify / AssetPipeline / ConditionalScript
/ SearchIndex tests and updated atomic-build/404 tests),
`check-contrast.py`, `npm run build`, `html-validate`, `test:a11y`
(+404), `test:layout`, `test:search`, `test:theme`, `test:404`,
`test:performance`, full `npm test`, `normalize_content.py --check`, and
the etsi-hash / word-diff integrity checks — all green.

## Integrity
- **No reproduced ETSI wording changed** (empty word-diff over
  `content/clause-*` / `content/annex-*`).
- **`data/etsi-content-hashes.json` unchanged.**
- **Source PDF bytes/checksum unchanged** — SHA-256
  `c2247f2d59c6f1465e5c10a8d6720aaa79c2d82a420435eb8f487e34dcc0672a`.
- Committed `docs/` matches a clean, deterministic rebuild.

## Deliberately deferred (not started)
CSP; service worker; immutable caching beyond fingerprinted assets;
custom domain / Cloudflare deploy or account changes; any wording,
licensing or publication-status change.
