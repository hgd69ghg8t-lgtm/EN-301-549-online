# Task 30 — JavaScript loading and execution

Spec requirements: **R-030, R-031, R-032** (C1–C6 apply).

Depends on: task 20 (JS source now at `assets/site.js`, hashed emit).

## Goal

The script loads without blocking and does minimal work at startup. No
behaviour change.

## Steps

1. Move the script tag from end-of-body to the head with `defer`
   (parser-non-blocking, executes in order after parse — same execution
   point as end-of-body but the browser discovers/fetches it early alongside
   the CSS instead of after parsing ~50–128 KB of HTML). Verify with a
   before/after trace on the largest page
   (`annex-za-directive-2016-2102.html`); if no observable benefit, keep
   end-of-body and record the measurement either way (R-030).
2. Audit `assets/site.js` init path (top-to-bottom IIFE):
   - Confirm all `querySelectorAll` calls are bounded and run once.
   - Confirm no layout reads interleaved with writes at startup (the
     scrollable-tables block reads `scrollWidth` — check it batches reads
     before writes).
   - Confirm listeners/features no-op cheaply on pages lacking their targets.
   - Fix only what the audit finds; do not restructure working code.
3. Do NOT split `site.js` into per-page bundles: one cached file serves all
   40 pages; the search-page-only code is already gated and inert elsewhere.
   Record as a considered-and-rejected split (results doc).
4. Rebuild; determinism check; hash changes ripple to every page (expected).

## Files changed

`assets/site.js`, `scripts/build.py` (script tag placement),
`scripts/test_build.py` (if it asserts script position), regenerated `docs/`.

## Tests to run

Full Python suite · build ×2 determinism · html-validate · `test:a11y` ·
`test:layout` · `test:search` · `test:theme` (theme suite asserts pre-paint
happens before first paint — the deferred script must not take over any
pre-paint duty; the inline head script keeps that job).

## Done criteria

- Script is `defer` in head (or measured justification for status quo);
  audit findings fixed and listed; all suites green; one focused commit.
