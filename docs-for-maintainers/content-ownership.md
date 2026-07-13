# Content ownership and periodic review

This site has no assigned content owner recorded yet. That's an honest gap, not an oversight to hide: `data/content-ownership.json` exists with every field set to `null` for the homepage, About page, and accessibility statement, and the build prints a note on every successful run listing which pages still have no governance metadata recorded. Nothing here should ever be filled in with an invented name, role, or date — leave a field `null` until a real maintainer actually sets it.

## The schema

`data/content-ownership.json` has one entry per website-authored page (`index`, `about`, `accessibility-statement` — the same set as `NON_STANDARD_SLUGS` in `scripts/build.py`). Each entry has six optional fields:

| Field | Meaning |
| --- | --- |
| `owner` | The person or team responsible for this page's content, if one has been assigned. |
| `ownerRole` | That person/team's role or job title, for context. |
| `lastReviewDate` | The date someone last reviewed this page's content for accuracy, in `YYYY-MM-DD` form. |
| `nextReviewDate` | A specific date this page is next due for review, in `YYYY-MM-DD` form (use this or `reviewFrequency`, not necessarily both). |
| `reviewFrequency` | A plain-text review cadence instead of a fixed date, e.g. `"annually"` or `"every 6 months"`. |
| `statusCheckDate` | The date someone last confirmed this specific page's content (as opposed to the ETSI source document's publication status, which is tracked separately in `data/source-metadata.json`) was still accurate. |

The build validates this file if it's present: unknown slugs or fields fail the build, as does a date that's malformed or an obvious placeholder (e.g. `"0000-00-00"`). A field left as `null` is always valid — that's the correct way to represent "not known yet."

**This metadata is not published on the website.** It's a maintainer-facing record only, consistent with "don't expose internal metadata publicly unless useful to users" — a reader of the accessibility statement doesn't need to see an internal review schedule, though nothing prevents a future decision to surface a "last reviewed" date publicly once real values exist.

## Periodic review checklist

When a maintainer actually reviews one of these pages, update its entry in `data/content-ownership.json` and work through this list:

- [ ] Re-read the page as a first-time visitor would, checking wording is still accurate and nothing has gone stale.
- [ ] For the homepage and About page: confirm the ETSI publication/approval status described still matches `data/source-metadata.json` and the linked ETSI deliverable page.
- [ ] For the accessibility statement: confirm the "Testing status" section still accurately reflects what has and hasn't actually been tested (see `docs-for-maintainers/accessibility-testing.md`'s test log) — do not let it silently drift into implying more testing has happened than has.
- [ ] Check every link on the page still resolves (the build's own `broken-anchor-link`/`broken-internal-link` checks cover same-site links; external links, e.g. to the ETSI website or GitHub, need a manual check).
- [ ] Set `lastReviewDate` to today's date (`YYYY-MM-DD`).
- [ ] Set `nextReviewDate` or `reviewFrequency` to when this page should next be reviewed.
- [ ] If you are that page's actual, current owner, set `owner` and `ownerRole` — otherwise leave them `null`.
- [ ] Run `python3 scripts/build.py` to confirm the updated file still validates.
