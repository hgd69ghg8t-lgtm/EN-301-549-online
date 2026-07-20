# Licensing

This repository contains material with different copyright and licensing
arrangements. Nothing in this file is a legal determination; it records how
the project licenses its own work and where other parties' rights begin.

## Software

Unless stated otherwise, the original software in this repository is
licensed under the MIT License.

This includes the Python build and validation scripts, JavaScript, CSS,
HTML templates, automated tests, GitHub Actions workflows, and the
configuration used to build and operate the website.

See [`LICENSE`](LICENSE).

## Original design and website-authored material

Unless stated otherwise, original design material, maintainer documentation
and website-authored explanatory material are licensed under the Creative
Commons Attribution 4.0 International Licence (CC BY 4.0,
https://creativecommons.org/licenses/by/4.0/).

Reuse must include appropriate attribution and identify whether changes
were made. Suggested attribution:

> AccessibleDocs website design and documentation, licensed under
> [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/).
> Changes were made.

See [`LICENSE-CONTENT.md`](LICENSE-CONTENT.md).

## ETSI material

The MIT and Creative Commons licences do **not** apply to:

- reproduced text from ETSI EN 301 549
- the ETSI source PDF (`source/`, published as a copy at `docs/source/`)
- ETSI copyright and legal notices
- ETSI trademarks, names or logos
- other material owned by ETSI or another third party

**Permission to reproduce and publish this material has not yet been
obtained from ETSI.**

The repository and website must not be treated as cleared for public
publication or redistribution of ETSI material until written permission and
its conditions have been received and recorded.

No right to reproduce, publish, redistribute or adapt ETSI material may be
inferred from the open licences covering the surrounding website. ETSI
material must retain ETSI's own attribution and notices — do not attribute
it to this project.

This repository currently contains, and if published would publicly serve,
ETSI material in several forms: the reproduced HTML standard, the ETSI
source PDF, ETSI excerpts in the search index, generated pages containing
ETSI text, and downloadable or cloneable copies of all of these through
GitHub itself. **None of these uses should be treated as authorised until
written permission is obtained.**

## ETSI permission record

Status: **Permission not yet obtained**

- Permission reference: `[NOT AVAILABLE]`
- Granted by: `[NOT AVAILABLE]`
- Date granted: `[NOT AVAILABLE]`
- Material covered: `[NOT YET CONFIRMED]`
- Website publication permitted: `[NOT YET CONFIRMED]`
- Source PDF hosting permitted: `[NOT YET CONFIRMED]`
- Public repository distribution permitted: `[NOT YET CONFIRMED]`
- Conditions or limitations: `[NOT YET CONFIRMED]`
- Record location: `[NOT AVAILABLE]`

This record is a governance document, not reader-facing website content.
Complete it only from actual written correspondence with ETSI — these
placeholders must not be replaced with assumptions.

## Branding

The AccessibleDocs name, wordmark and combined project logo are reserved
unless expressly stated otherwise.

The open licences allow reuse of the underlying code and visual design, but
do not grant permission to present a modified or third-party website as the
original AccessibleDocs service.

Generic design patterns and non-branded interface components remain covered
by the applicable open licence.

## Fonts

The site no longer distributes any webfont. Typography uses the reader's
own system fonts via a CSS system-font stack (see `assets/css/style.css`),
so no font files are stored in the repository or published under `docs/`,
and no font-licence obligations apply. (Earlier versions self-hosted
Overpass and Source Sans 3 under `assets/fonts/`; those files were removed
when the site moved to system fonts.) Re-verify the licence of any font
added later before self-hosting it.

## Third-party material

Any other third-party material retains its own copyright and licence terms.
Where third-party material is added, it must be clearly identified and must
not be presented as covered by the project's licences.

## Publication-readiness checklist

**This section states facts and open questions. It does not make a legal
determination, and nothing below should be read as one.** Do not treat
this site as ready for public release until every item below is either
checked or explicitly waived by whoever is accountable for that decision.

- [ ] **Written permission from ETSI to reproduce and publish the standard has been obtained.** *(Required — this remains a publication blocker; every other item on this list only matters once this one is genuinely true.)*
- [ ] The permission reference, grantor, date, scope, permitted publication channels and applicable conditions have been recorded in the ETSI permission record above, from the actual correspondence.
- [ ] Permission to host and distribute the ETSI source PDF has been specifically confirmed.
- [ ] Permission for ETSI material to remain in a publicly cloneable and forkable repository has been specifically confirmed.
- [x] A licence has been chosen and recorded for this site's own code/design (MIT for software, CC BY 4.0 for original design/documentation — see `LICENSE`, `LICENSE-CONTENT.md`, and the sections above), and each statement of it is explicit that it does not extend to the reproduced ETSI text or to the trademarks named in it. *(The `LICENSE` file's `[COPYRIGHT HOLDER]` placeholder still needs the legal copyright holder's name.)*
- [ ] `npm test` (the complete suite: static checks plus the Playwright browser suites — a11y, layout, search, theme, 404, performance) passes on the commit being published.
- [ ] `python3 scripts/build.py` then `git status --porcelain -- docs/` prints nothing (committed `docs/` matches a fresh rebuild, with no stale or missing files).
- [x] The accessibility statement has a real reporting route (currently a GitHub issues link — replace with a dedicated contact address if/when one exists).
- [ ] The accessibility statement's "Review history" section has at least one real, completed review recorded.
- [ ] A genuine manual accessibility test pass has been completed against `docs-for-maintainers/accessibility-testing.md`, and its log updated.
- [ ] `data/source-metadata.json`'s checksum has been re-verified against the currently committed source PDF.
