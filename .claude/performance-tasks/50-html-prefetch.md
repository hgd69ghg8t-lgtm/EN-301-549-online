# Task 50 — HTML head hygiene and navigation prefetch

Spec requirements: **R-050, R-051, R-052** (C1–C6 apply).

Depends on: tasks 10–40 (head contents final before ordering is asserted).

## Goal

Sequential reading (the dominant journey for a standard) gets near-instant
prev/next navigation via static prefetch hints; the head is in a deliberate,
tested order.

## Steps

1. In `scripts/build.py`, the pager already computes prev/next per page —
   reuse that to emit `<link rel="prefetch" href="{prev}">` /
   `<link rel="prefetch" href="{next}">` in the head (skip missing ends;
   index/search/about pages get whatever their pager defines — if they have
   no pager, no prefetch). Static hints only: browsers deprioritise them,
   skip on data-saver, and they're ignored without harm (R-050).
2. Head order review (R-051), final order: charset/viewport → title/meta
   description → theme-color metas → inline pre-paint script → OG/twitter
   metas → canonical → stylesheet → font preloads → icons → prefetch links.
   Justify or remove anything outside this list. (Pre-paint-before-
   stylesheet is already unit-tested — keep those tests authoritative.)
3. Extend `scripts/test_build.py` (R-052): every content page with a pager
   carries correct prefetch hrefs (match the pager's own links); head-order
   assertions for stylesheet-before-font-preloads and preloads-before-
   prefetch.
4. Rebuild ×2; determinism. Confirm html-validate accepts the prefetch links
   and `test:layout`/`test:a11y` are unaffected (prefetch is head-only,
   invisible).
5. Measure: per-page HTML byte delta from the added links (~150 B/page —
   record honestly); note that transfer benefit shows as warm-cache
   navigation, verifiable in `test-perf.mjs` (task 60) if practical.

## Files changed

`scripts/build.py`, `scripts/test_build.py`, regenerated `docs/*.html`.

## Tests to run

Full Python suite · build ×2 determinism · html-validate · `test:layout` ·
`test:a11y` · `test:theme` · `perf-report.py` snapshot.

## Done criteria

- Prev/next prefetch on every paged page, matching the pager exactly;
  head order asserted in unit tests; all suites green; one focused commit.
