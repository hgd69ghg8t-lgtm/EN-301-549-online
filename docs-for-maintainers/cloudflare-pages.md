# Cloudflare Pages deployment (prepared, NOT active)

This repository is *prepared* for a Cloudflare Pages deployment, but no
Cloudflare deployment exists today and none is claimed. **The committed
canonical production domain remains GitHub Pages**
(`baseUrl` in `data/site-config.json`) **until a real custom domain is
deliberately selected and configured** — do not change the canonical
domain speculatively, and do not invent one.

What "prepared" means concretely:

- `deployment/cloudflare/_headers` and `deployment/cloudflare/_redirects`
  are hand-authored source files the build copies verbatim to
  `docs/_headers` and `docs/_redirects` (validated at build time — see
  `validate_redirects()` in `scripts/build.py`). GitHub Pages ignores
  both files; Cloudflare Pages reads them from the output directory.
- The build generates an accessible custom `docs/404.html` (shared site
  design, `noindex`, absolute links) that both GitHub Pages and
  Cloudflare Pages serve automatically for missing paths.
- `docs/.nojekyll` is generated so GitHub Pages serves the
  underscore-prefixed files instead of dropping them.

## Setting up the Git integration

1. In the Cloudflare dashboard: **Workers & Pages → Create → Pages →
   Connect to Git**, and select this repository.
2. Configure the project:
   - **Framework preset:** None
   - **Build command:** `python3 scripts/build.py`
     (or, because `docs/` is committed and CI verifies it matches a clean
     rebuild, the build command can be left empty and the committed
     output served as-is; running the build is the safer default)
   - **Build output directory:** `docs`
   - **Production branch:** the repository's default branch
3. No environment variables are required — a reproducible production
   build must not depend on any (the build reads only committed files).

Preview deployments: Cloudflare builds every non-production branch/PR at
a unique `*.pages.dev` preview URL by default. Previews are useful for
review, but note the canonical URLs inside the pages still point at the
committed `baseUrl` — that is correct behaviour (previews should not
present themselves as the production site).

## Switching the canonical domain (only when a real domain exists)

1. Add the custom domain to the Pages project (**Custom domains** tab)
   and complete the DNS verification.
2. Update `data/site-config.json`: set `baseUrl` to the new HTTPS URL
   (must end in `/`), and set `deploymentTarget` to `cloudflare-pages`.
3. Rebuild (`npm run build`) and re-run the full suite (`npm test`).
4. Check the regenerated output before committing:
   - `rel="canonical"` and `og:url` on any page carry the new domain;
   - `docs/sitemap.xml` and `docs/robots.txt` carry the new domain;
   - the `docs/404.html` links are absolute under the new domain.
5. Commit the configuration change together with the regenerated `docs/`.
6. After the deployment goes live, verify (see below) before announcing
   anything.

## Duplicate-host handling (`*.pages.dev`)

Cloudflare always serves the project at `<project>.pages.dev` in
addition to any custom domain, so the same content exists at two hosts.
The canonical links generated from `data/site-config.json` already point
search engines at the one intended host. If stronger separation is
wanted later, add a redirect ruleset (a Cloudflare Bulk Redirect or a
`_redirects` rule set on the pages.dev host) sending `*.pages.dev`
requests to the custom domain — do this only after the custom domain is
live and verified.

## `_headers`

`deployment/cloudflare/_headers` currently sets a conservative security
baseline (`X-Frame-Options: DENY`, `X-Content-Type-Options: nosniff`,
`Referrer-Policy: strict-origin-when-cross-origin`, and a
`Permissions-Policy` disabling powerful features this site never uses).

Two deliberate deferrals, documented here so they aren't "fixed" casually:

- **No Content-Security-Policy yet.** The pages carry an inline
  pre-paint theme script. A CSP must be designed with hashes or nonces
  and tested against that script, the local assets, external ETSI
  links, print output, and every Playwright suite before it ships.
  Adding `'unsafe-inline'` merely to make a CSP pass would reduce it to
  theatre, so there is no CSP at all until it can be done properly.
- **No one-year `immutable` caching.** Asset filenames are not
  fingerprinted — `assets/css/style.css` keeps its name across releases
  and only its `?v=` query changes. Immutable caching of an unhashed
  filename can pin visitors to stale assets after a release. Long-lived
  caching waits until fingerprinted (content-hashed) filenames exist.

## `_redirects`

`deployment/cloudflare/_redirects` contains no active rules — this site
has never renamed a published URL, and old URLs must not be invented.
The historical accessibility-statement move is already handled by a
generated meta-refresh stub that works on any static host. When a real
rule is ever needed, the build validates it: rooted `/source`, local or
HTTPS target, supported status (301/302/303/307/308), no duplicate
sources, no detectable loops.

## Rollback

Cloudflare Pages keeps every previous deployment. To roll back:
**the Pages project → Deployments → (previous good deployment) →
Manage → Rollback to this deployment**. Because the site is fully
static and generated from a committed `docs/`, rolling back the Git
branch (revert commit, push) achieves the same thing through the normal
build path and keeps Git as the source of truth — prefer that when time
allows.

## Verification after any deployment

- Load the homepage, one long clause (e.g. clause 9), the About page and
  the search page over the deployed host; check styling, fonts and the
  theme toggle work (i.e. `_headers` broke nothing).
- Request a nonsense URL and confirm the custom 404 page appears, with
  working Home/Search links.
- Confirm `curl -sI https://<host>/` shows the security headers (on
  Cloudflare only — GitHub Pages does not serve `_headers`).
- Confirm `https://<host>/source/en_301549v040100va.pdf` downloads and
  its `sha256sum` matches `data/source-metadata.json`.
- Check `rel="canonical"`, `og:url`, `sitemap.xml` and `robots.txt`
  reference the intended canonical host (see `data/site-config.json`).
- Run the browser suites against the deployed host manually if anything
  looks off (the automated suites run against a local server of the same
  files).
