# Task 70 — Final verification and results

Spec requirements: **R-070, R-071, R-072, R-073, R-074** (C1–C6 apply).

Depends on: all prior tasks complete.

## Goal

Prove the project's claims, document everything, and present the branch —
without opening or merging a pull request.

## Steps

1. Full regression (R-070), fresh run, results recorded verbatim:
   `python3 -m unittest scripts/test_build.py` ·
   `python3 scripts/check-contrast.py` · `npm run build` ·
   `git diff --exit-code -- docs/` · `npx html-validate "docs/*.html"` ·
   `python3 scripts/perf-report.py --budget` · `npm run test:a11y` ·
   `npm run test:layout` · `npm run test:search` · `npm run test:theme` ·
   `npm run test:perf`.
2. Determinism, directly (R-071): from a clean tree run the build twice into
   the working tree and confirm `git status`/diff show no change between
   runs (and vs the committed docs/).
3. ETSI integrity (R-072): build validation green (it hash-checks protected
   fragments) AND `git diff <baseline-commit>..HEAD -- content/
   data/etsi-content-hashes.json` is empty, where `<baseline-commit>` is the
   commit recorded by task 00. Also spot-check one reproduced page's visible
   wording against the baseline commit (`git show`) as a human-level check.
4. Comparison (R-073 input): `perf-report.py --json` final snapshot vs
   `.claude/performance-tasks/baseline.json`; build the before/after table
   (raw + gzip: CSS, JS, fonts, indexes, worst/median page, first-visit
   weight, first-keystroke search cost).
5. Write `docs/performance-optimisation-results.md` (R-073):
   - measured improvements (the table + per-task notes);
   - tests and results (the full list from step 1 with outcomes);
   - accessibility verification (axe suites, html-validate, no-JS behaviour,
     theme/contrast checks);
   - implementation decisions (hashed filenames, CSS-only minification,
     titles/full index split, defer decision, prefetch scope);
   - rejected optimisations (spec §4 plus anything added en route, each with
     reasons);
   - deviations from the specification (including its drafted-not-supplied
     provenance);
   - remaining risks (e.g. GitHub Pages 10-minute cache on hashed assets,
     minifier conservatism, budget-update discipline).
6. Update `.claude/performance-progress.md`: all tasks complete, final
   numbers, nothing outstanding.
7. Commit ("Performance optimisation: final verification and results"),
   push, and present the branch summary to the maintainer. **Do not open a
   PR; do not merge** (R-074).

## Done criteria

- Every suite green in the final run; determinism and ETSI integrity shown,
  not assumed; results doc complete and honest (including what did NOT
  improve); branch pushed; no PR/merge.
