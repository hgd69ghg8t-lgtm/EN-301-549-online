# Performance optimisation — progress

Branch: `claude/performance-optimization-planning-ofj09d`
Spec (binding): `docs/performance-optimisation-spec.md`
Task files: `.claude/performance-tasks/00…70`

## Status

| Task | Title | State | Commit | Tests run | Notes |
|------|-------|-------|--------|-----------|-------|
| 00 | Baseline + measurement tooling | not started | — | — | — |
| 10 | Fonts and theme paint | not started | — | — | — |
| 20 | Asset pipeline + hashed filenames | not started | — | — | — |
| 30 | JavaScript loading/execution | not started | — | — | — |
| 40 | Search index split + size | not started | — | — | — |
| 50 | HTML head + prefetch | not started | — | — | — |
| 60 | Perf suite, budgets, CI, docs | not started | — | — | — |
| 70 | Final verification + results | not started | — | — | — |

Planning stage: **complete** — spec drafted from repository analysis (the
commissioning message's attached spec was missing; maintainer approved
drafting it), task files created, all committed to the branch above.

## Baseline measurements

_To be filled by task 00 (R-001/R-002) before any production change._

## Outstanding failures

None known. `node_modules` is not installed in a fresh container — run
`npm ci && npx playwright install chromium` before the Playwright suites
(Chromium is pre-installed in Claude remote containers at
`/opt/pw-browsers`; do NOT run `playwright install` there — see the
container notes).

## Next task

`00-baseline.md` — awaiting the maintainer's instruction to begin
implementation.

## Context-handoff notes (keep current)

If a fresh session picks this up:

1. Read `docs/performance-optimisation-spec.md` (binding constraints C1–C6),
   this file, and the next not-started task file. Do **not** redo
   repository-wide analysis — the spec's findings and the task files carry it.
2. Repository shape: static site; `scripts/build.py` (Python stdlib only)
   renders `content/*.html` fragments into `docs/` (GitHub Pages).
   Determinism is CI-enforced (rebuild must not diff). ETSI wording is
   hash-protected (`data/etsi-content-hashes.json` — never touch, never run
   `update_etsi_hashes.py`).
3. Work sequentially through the task files; one focused commit per task;
   push with `git push -u origin claude/performance-optimization-planning-ofj09d`.
4. Update this file after every task: state, commit hash, tests run,
   measurements, failures, next task, exact files needing attention.
