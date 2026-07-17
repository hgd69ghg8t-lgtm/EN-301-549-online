# Performance optimisation — progress

Branch: `claude/performance-optimization-planning-ofj09d`
Spec (binding): `docs/performance-optimisation-spec.md`
Task files: `.claude/performance-tasks/00…70`

## Status

| Task | Title | State | Commit | Tests run | Notes |
|------|-------|-------|--------|-----------|-------|
| 00 | Baseline + measurement tooling | **complete** | (this commit) | full suite green: unittest, contrast, build+diff, html-validate, a11y, layout, search, theme | baseline in `baseline.json` + task file |
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

Recorded by task 00 on commit `846f69a`; full snapshot in
`.claude/performance-tasks/baseline.json`, tables in
`.claude/performance-tasks/00-baseline.md`. Headlines (gzip = wire size):

- CSS 50.5 KB raw / 13.3 KB gzip · JS 31.9 KB raw / 9.2 KB gzip
- Fonts 66.5 KB on the wire (2 × WOFF2, pre-compressed)
- Search index 719.8 KB raw / **129.5 KB gzip** = first-keystroke cost of
  the header search on every page (the project's biggest target)
- Worst first visit 110.6 KB (`clause-11-non-web-software.html`);
  median 96.7 KB; total site raw 2568.7 KB (PDF excluded)

## Outstanding failures

None known. Fresh-container setup learned during task 00: run `npm ci`,
then run the Playwright suites with
`PLAYWRIGHT_CHROMIUM_PATH=/opt/pw-browsers/chromium` — the container's
pre-installed Chromium build (1194) predates the one the pinned Playwright
wants (1228), and the suites already support this env var precisely for
that. Do NOT run `npx playwright install` in the container. CI is
unaffected (it installs its own Chromium).

## Next task

`10-fonts-theme.md` — awaiting the maintainer's instruction (task 00 was
authorised and completed on its own; do not start 10 unprompted).

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
