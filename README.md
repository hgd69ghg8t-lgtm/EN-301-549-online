# EN 301 549 Online

An accessible, WCAG 2.2 AA-conformant HTML edition of *ETSI EN 301 549 V4.1.0: Accessibility requirements for ICT products and services*, styled with tokens from the [NZ Government Design System](https://github.com/GOVTNZ/govtnz-design-system) and structured similarly to [legislation.govt.nz](https://www.legislation.govt.nz/act/public/1991/69/en/latest/) (one page per clause/annex, persistent contents menu, in-page table of contents, prev/next navigation).

## Project structure

```
source/           Source PDF
content/<slug>.html   Hand-transcribed body-only HTML fragments (one per page), sourced from the PDF
scripts/sitemap.json  Ordered list of every page: slug, title, group, source PDF page range
scripts/build.py      Wraps each content/*.html fragment in the shared template and writes docs/*.html
docs/             Generated static site (published via GitHub Pages) — do not hand-edit, run the build instead
```

## Building the site

```
python3 scripts/build.py
```

This regenerates every file in `docs/*.html` from `content/*.html` + `scripts/sitemap.json`. The shared page template (header, skip link, breadcrumb, sidebar site navigation, in-page "On this page" contents, prev/next pager, footer) lives inline in `scripts/build.py`; `docs/assets/css/style.css` holds the design tokens and styling. Pages without a matching `content/<slug>.html` file are built as "not yet converted" placeholders so the full site map always resolves.

## Adding a new converted page

1. Find the page's entry in `scripts/sitemap.json` for its PDF page range.
2. Extract the source text: `pdftotext -layout -f <start> -l <end> source/en_301549v040100va.pdf -`
3. Transcribe it into `content/<slug>.html` as a semantic body fragment: `<h1>` once, `<h2>`/`<h3>` with `id` attributes for subclauses (these drive the in-page contents), `<p>`, `<ul>/<ol>`, `<dl>` for definitions, `<table>` (wrapped in `<div class="table-wrap">`) for tables, and `<div class="callout"><p><span class="callout__label">NOTE:</span> ...</p></div>` for NOTE/EXAMPLE callouts.
4. Run the build.

## Accessibility

Colour pairs are verified against WCAG 2.2 AA contrast thresholds (4.5:1 text, 3:1 UI components) — see `docs/assets/css/style.css` header comment for the source tokens. Pages are checked with `axe-core` against the wcag2a/wcag2aa/wcag22aa rule sets.

## Hosting

This site is published for free via GitHub Pages, serving from the `docs/` folder. Once this branch is merged to the default branch, enable it under **Settings → Pages → Source: Deploy from a branch → (default branch) /docs**.
