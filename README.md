# EN 301 549 Online

An accessible, WCAG 2.2 AA-conformant HTML edition of *ETSI EN 301 549 V4.1.0: Accessibility requirements for ICT products and services*, styled with tokens from the [NZ Government Design System](https://github.com/GOVTNZ/govtnz-design-system) and structured similarly to [legislation.govt.nz](https://www.legislation.govt.nz/act/public/1991/69/en/latest/) (one page per clause/annex, a single persistent left-hand contents sidebar covering both the site-wide page list and the current page's own subsections, prev/next navigation).

## Project structure

```
content/           36 body-only HTML fragments — the actual transcribed standard
                    text (headings, paragraphs, lists, tables, callouts). This is
                    what you hand-edit.
scripts/
  build.py          The build script. Wraps each content/ fragment in the shared
                    page template (skip link, header, breadcrumb, contents
                    sidebar, prev/next pager, footer) and writes docs/*.html.
  sitemap.json      Single source of truth for the site's 36 pages: slug, title,
                    nav group, and the source PDF page range each page was
                    transcribed from.
docs/               Generated output, served by GitHub Pages. Never hand-edited —
                    re-run the build instead. Also holds the static, hand-authored
                    docs/assets/css/style.css and docs/assets/js/site.js.
source/             The original ETSI source PDF.
design/             Figma Make export used as the visual reference for the site's
                    design system. Not read by the build.
```

## Building the site

The build has no dependencies beyond the Python 3 standard library:

```
python3 scripts/build.py
```

This reads `scripts/sitemap.json` and `content/*.html` and regenerates every file under `docs/`. Re-run it after editing anything in `content/`.

To extract new content from the source PDF, you'll also need [`pdftotext`](https://poppler.freedesktop.org/) (from the `poppler-utils` package — not installed by default on a clean machine):

```
apt-get install poppler-utils   # Debian/Ubuntu
brew install poppler            # macOS
```

## Content-authoring conventions

- Heading elements must carry `id="..."` as the **first** attribute after the tag name (e.g. `<h2 id="scope">`, not `<h2 class="foo" id="scope">`) — the build script's heading extractor is regex-based and keys the contents sidebar off this exact pattern. A heading that doesn't follow it will silently disappear from navigation with no build error.
- Content fragments are body-only: no `<html>`, `<head>`, or `<body>` tags — the build template supplies those.

## Accessibility

Colour pairs are verified against WCAG 2.2 AA contrast thresholds (4.5:1 text, 3:1 UI components) — see `docs/assets/css/style.css` header comment for the source tokens. Pages are checked with `axe-core` against the wcag2a/wcag2aa/wcag22aa rule sets.

## Hosting

This site is published for free via GitHub Pages, serving from the `docs/` folder. Once this branch is merged to the default branch, enable it under **Settings → Pages → Source: Deploy from a branch → (default branch) /docs**.
