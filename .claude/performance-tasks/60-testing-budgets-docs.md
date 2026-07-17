# Task 60 — Performance regression suite, budgets, CI and docs

Spec requirements: **R-060, R-061, R-062, R-063** (C1–C6 apply).

Depends on: tasks 00–50 (budgets are set from the final measured sizes).

## Goal

Performance becomes a regression-tested property: hard size budgets in CI, a
browser-level perf suite, and maintainer documentation.

## Steps

1. `scripts/perf-report.py --budget` (R-060): budgets defined in one obvious
   dict at the top of the file, gzipped bytes, set to post-task-50 measured
   values plus stated headroom (~15–20 %): CSS, JS, each font (raw — already
   compressed), titles index, full index, worst-page HTML, worst-page
   first-visit weight. Breach → named failure, non-zero exit. Include a
   short comment: how to change a budget deliberately (echoing the ETSI-hash
   philosophy: never bump just to silence a failure).
2. `scripts/test-perf.mjs` (R-061), mirroring the structure of the existing
   `.mjs` suites (local static server + Playwright Chromium):
   - sample pages (index, largest page, clause-3 glossary, search.html):
     zero console errors;
   - type in the header search on a content page → network sees the titles
     index only, never `search-index.json`;
   - open `search.html` and search → full index fetched there (once);
   - stylesheet/script URLs on each sampled page match
     `style.<hash>.css` / `site.<hash>.js` naming and return 200;
   - record (informational, not asserted) DOMContentLoaded on the sampled
     pages.
3. `package.json`: add `"test:perf": "node scripts/test-perf.mjs"` and a
   `"perf": "python3 scripts/perf-report.py"` convenience; wire the budget
   check into the main `npm test` chain only if runtime is trivial
   (it is — pure file reads), else keep it a separate CI step.
4. `.github/workflows/ci.yml` (R-062): add steps "Performance budgets
   (gzipped sizes)" (`python3 scripts/perf-report.py --budget`) after the
   rebuild-diff step, and "Performance behaviour checks" (`npm run
   test:perf`) after the theme suite. Update the workflow's top comment
   block (it documents the run order).
5. Docs (R-063): README section on the perf pipeline + budgets;
   `docs-for-maintainers/performance.md` (new): running the report, reading
   it, updating budgets deliberately, what test-perf covers.

## Files changed

`scripts/perf-report.py`, `scripts/test-perf.mjs` (new), `package.json`,
`.github/workflows/ci.yml`, `README.md`,
`docs-for-maintainers/performance.md` (new).

## Tests to run

`python3 scripts/perf-report.py --budget` (passes with headroom) · `npm run
test:perf` · full Python suite · build determinism · html-validate · all
four existing Playwright suites (regression) .

## Done criteria

- Budgets enforce measured reality with headroom; perf suite green locally;
  CI updated (verifiable on push); docs written; one focused commit.
