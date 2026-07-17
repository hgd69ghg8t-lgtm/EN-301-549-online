# Task 20 — Asset pipeline: hashed filenames + CSS minification

Spec requirements: **R-020, R-021, R-022, R-023, R-024** (C1–C6 apply).

Depends on: task 10 (template head settled). Tasks 30/40 depend on this
(they edit the relocated JS source).

## Goal

CSS/JS become build outputs with content-hashed filenames (atomic rollout,
cache-safe), CSS is minified, and the hand-authored sources move out of the
generated tree.

## Steps

1. Create top-level `assets/` source dir; `git mv docs/assets/css/style.css
   assets/style.css` and `git mv docs/assets/js/site.js assets/site.js`.
   Add a short `assets/README.md` (authored sources; build emits hashed,
   CSS-minified copies into `docs/assets/`).
2. In `scripts/build.py`:
   - Replace `asset_version()` query-string use with an emit step: read
     `assets/style.css`, minify (step 3), hash the **emitted** bytes
     (SHA-256, first 8 hex chars), write `docs/assets/css/style.<hash>.css`;
     same for `assets/site.js` (no minification, R-023) →
     `docs/assets/js/site.<hash>.js`. Template references the hashed names;
     drop `?v=`.
   - Before writing, delete stale `docs/assets/css/style.*.css` /
     `docs/assets/js/site.*.js` so exactly one of each exists (keeps the CI
     rebuild-diff meaningful).
   - Fonts/images keep stable names (they change ~never; renaming would
     churn every page).
3. CSS minifier (stdlib, conservative, deterministic): strip `/* … */`
   comments, collapse runs of whitespace, trim around `{};:,>` — **no**
   property/selector rewriting, no colour transforms. Must preserve strings
   and `content:` values (walk the text respecting quotes rather than blind
   regex). Unit-test it in `scripts/test_build.py` (comment stripped,
   string with `/*` preserved, output stable).
4. Update every consumer of the old paths:
   - `scripts/check-contrast.py` → parse `assets/style.css` (the source).
   - `scripts/test_build.py` → template/head assertions target hashed names
     (glob/regex).
   - Playwright suites: they navigate pages (paths resolve themselves) —
     grep `scripts/*.mjs` for hardcoded `assets/` paths and fix any.
   - `README.md`, `docs-for-maintainers/maintenance.md`, `assets/README.md`,
     the `asset_version()` doc-comment area: describe the new pipeline.
   - Check `.htmlvalidate.json` and `.gitignore` need nothing.
5. Rebuild twice; byte-identical. Verify only one hashed CSS/JS pair exists
   in `docs/assets/`.

## Risks / notes

- The CSS-minifier is the riskiest piece: keep it dumb; rely on the contrast
  checker (parses source now), html-validate, and the four browser suites to
  catch breakage. `test:theme` exercises computed styles — good canary.
- The fonts README (`docs/assets/fonts/README.md`) has a relative link
  `../../../LICENSES.md` — unaffected, but confirm nothing else links to
  `docs/assets/css/style.css` literally (grep the repo).

## Files changed

`assets/style.css` + `assets/site.js` (moved), `assets/README.md` (new),
`scripts/build.py`, `scripts/check-contrast.py`, `scripts/test_build.py`,
possibly `scripts/*.mjs`, `README.md`, `docs-for-maintainers/maintenance.md`,
regenerated `docs/` (all pages + new hashed assets, old unhashed files
removed).

## Tests to run

Full Python suite · `npm run build` ×2 + determinism diff · html-validate ·
all four Playwright suites · `scripts/perf-report.py` (CSS gzip before/after
minification — record the number).

## Done criteria

- Pages reference `style.<hash>.css` / `site.<hash>.js`; no `?v=` remains.
- `docs/assets/` CSS/JS is purely generated; sources live in `assets/`.
- Measured CSS size drop recorded; all suites green; one focused commit.
