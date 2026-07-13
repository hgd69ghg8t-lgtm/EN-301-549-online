# EN 301 549 Online

An accessible, WCAG 2.2 AA-conformant HTML edition of *ETSI EN 301 549 V4.1.0: Accessibility requirements for ICT products and services*, styled with tokens from the [NZ Government Design System](https://github.com/GOVTNZ/govtnz-design-system) and structured similarly to [legislation.govt.nz](https://www.legislation.govt.nz/act/public/1991/69/en/latest/) (one page per clause/annex, persistent contents menu, in-page table of contents, prev/next navigation).

## Accessibility

Colour pairs are verified against WCAG 2.2 AA contrast thresholds (4.5:1 text, 3:1 UI components) — see `docs/assets/css/style.css` header comment for the source tokens. Pages are checked with `axe-core` against the wcag2a/wcag2aa/wcag22aa rule sets.

## Hosting

This site is published for free via GitHub Pages, serving from the `docs/` folder. Once this branch is merged to the default branch, enable it under **Settings → Pages → Source: Deploy from a branch → (default branch) /docs**.
