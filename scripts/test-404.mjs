#!/usr/bin/env node
// End-to-end checks for the generated 404 page — a special generated
// page that is deliberately NOT in the sitemap, search or navigation,
// so the sitemap-driven suites never see it. Covers a direct visit to
// /404.html and real missing URLs (the local server serves the custom
// 404 page with status 404, like static hosting), and asserts:
//   - no runtime errors and every same-site asset request succeeds
//     (the page's URLs are absolute under the production baseUrl;
//     routeSiteBaseUrl maps that origin onto the local docs/ tree);
//   - exactly one visible <h1>, noindex, no canonical, no auto-redirect;
//   - the Page tools keep data-action="print" / data-action="copy-link"
//     exactly, Print reaches window.print(), Copy announces in the
//     live region;
//   - the Home / Search / Clause 1 links work;
//   - keyboard access to the main navigation and the page tools.
// Requires a Chromium install (same as test-a11y.mjs).
// Usage: node scripts/test-404.mjs
import {
  startServer, launchBrowser, routeSiteBaseUrl,
  trackRuntimeIssues, reportRuntimeIssues, SITE_BASE_URL,
} from "./browser-test-lib.mjs";

const server = await startServer();
const port = server.address().port;
const base = `http://127.0.0.1:${port}`;
const browser = await launchBrowser();
const fails = [];
const issues = [];
const check = (ok, msg) => { console.log((ok ? "ok   " : "FAIL ") + msg); if (!ok) fails.push(msg); };

// The three entry points: the page itself, and two real missing URLs
// (one nested — the case absolute links exist for).
const VISITS = [
  { path: "/404.html", expectStatus: 200 },
  { path: "/this-page-does-not-exist", expectStatus: 404 },
  { path: "/nested/path/that-does-not-exist", expectStatus: 404 },
];

// When the main document itself is fetched over a missing URL, the
// browser emits its own "Failed to load resource … 404" console error
// for that navigation. That 404 status is the behaviour under test, not
// a site defect, so it is allowed ONLY where we deliberately navigate to
// a missing URL — never on the directly served 200 page.
const ALLOW_NAV_404_CONSOLE = {
  kind: "console",
  test: (text) => /Failed to load resource.*404/i.test(text),
};

async function newPage(label, extraAllow = []) {
  const context = await browser.newContext({ viewport: { width: 1280, height: 900 } });
  await context.grantPermissions(["clipboard-read", "clipboard-write"], { origin: base });
  await routeSiteBaseUrl(context);
  const page = await context.newPage();
  trackRuntimeIssues(page, issues, {
    label,
    allow: [
      // The deliberate missing-URL navigations MUST return 404 — that
      // status is the behaviour under test, not a failure.
      { kind: "response", test: ({ url, status }) => status === 404 && VISITS.some((v) => url.endsWith(v.path)) },
      ...extraAllow,
    ],
  });
  return { context, page };
}

for (const visit of VISITS) {
  const extraAllow = visit.expectStatus === 404 ? [ALLOW_NAV_404_CONSOLE] : [];
  const { context, page } = await newPage(visit.path, extraAllow);
  const response = await page.goto(`${base}${visit.path}`, { waitUntil: "networkidle" });
  check(response.status() === visit.expectStatus,
    `${visit.path} returns HTTP ${visit.expectStatus} (got ${response.status()})`);

  const state = await page.evaluate(() => ({
    h1s: Array.from(document.querySelectorAll("h1"))
      .filter((h) => h.getClientRects().length > 0)
      .map((h) => h.textContent.trim()),
    robots: document.querySelector('meta[name="robots"]')?.content || null,
    canonical: document.querySelector('link[rel="canonical"]') !== null,
    metaRefresh: document.querySelector('meta[http-equiv="refresh" i]') !== null,
    title: document.title,
    stylesApplied: getComputedStyle(document.querySelector(".site-header")).backgroundColor,
    printAction: document.querySelector(".page-tools [data-action='print']") !== null,
    copyAction: document.querySelector(".page-tools [data-action='copy-link']") !== null,
    rewrittenDataAction: document.querySelector("[data-action^='https://']") !== null,
  }));
  check(state.h1s.length === 1 && state.h1s[0] === "Page not found",
    `${visit.path}: exactly one visible <h1> "Page not found" (got ${JSON.stringify(state.h1s)})`);
  check(state.robots === "noindex", `${visit.path}: noindex is present`);
  check(!state.canonical, `${visit.path}: no canonical link`);
  check(!state.metaRefresh, `${visit.path}: no automatic meta-refresh redirect`);
  check(state.title.includes("Page not found"), `${visit.path}: page title says Page not found`);
  check(state.stylesApplied !== "rgba(0, 0, 0, 0)",
    `${visit.path}: the stylesheet loaded and applied (header has a background)`);
  check(state.printAction, `${visit.path}: Print button keeps data-action="print" exactly`);
  check(state.copyAction, `${visit.path}: Copy button keeps data-action="copy-link" exactly`);
  check(!state.rewrittenDataAction, `${visit.path}: no data-action value was rewritten to a URL`);

  // System fonts only: no webfont is downloaded, and the body resolves
  // to a real system sans-serif stack (so text is legible immediately
  // with no font-swap reflow).
  const bodyFont = await page.evaluate(() => getComputedStyle(document.body).fontFamily);
  check(/system|Segoe UI|Roboto|Helvetica|Arial|sans-serif/i.test(bodyFont),
    `${visit.path}: body uses a system-font stack (got ${bodyFont})`);

  // The URL must not change on its own (no scripted redirect either).
  await page.waitForTimeout(500);
  check(page.url() === `${base}${visit.path}`, `${visit.path}: no automatic redirect happened`);

  // Expected same-site links, absolute under the configured base URL.
  const links = await page.evaluate(() => {
    const grab = (text) =>
      Array.from(document.querySelectorAll(".content a"))
        .find((a) => a.textContent.includes(text))?.getAttribute("href") || null;
    return { home: grab("Home page"), search: grab("Search this standard"), clause1: grab("Clause 1") };
  });
  check(links.home === `${SITE_BASE_URL}index.html`, `${visit.path}: Home link is absolute`);
  check(links.search === `${SITE_BASE_URL}search.html`, `${visit.path}: Search link is absolute`);
  check(links.clause1 === `${SITE_BASE_URL}clause-1-scope.html`, `${visit.path}: Clause 1 link is absolute`);
  await context.close();
}

// ---- Page tools behaviour (on the directly served 404 page) ----
{
  const { context, page } = await newPage("page-tools");
  await page.goto(`${base}/404.html`, { waitUntil: "networkidle" });

  // Print: stub window.print (headless print dialogs are not real) and
  // confirm the click reaches the handler page-tools.js bound to
  // [data-action='print'].
  await page.evaluate(() => {
    window.__printCalls = 0;
    window.print = () => { window.__printCalls += 1; };
  });
  await page.click(".page-tools > summary");
  await page.click(".page-tools [data-action='print']");
  check(await page.evaluate(() => window.__printCalls) === 1,
    "clicking Print invokes the window.print() handler");

  // Copy: the shared live region announces the confirmation.
  await page.click(".page-tools [data-action='copy-link']");
  await page.waitForFunction(
    () => /copied/i.test(document.getElementById("status-live").textContent),
    null, { timeout: 5000 });
  check(true, "clicking Copy announces a confirmation in the live region");
  const clipboard = await page.evaluate(() => navigator.clipboard.readText());
  check(clipboard === page.url(), `Copy put the page address on the clipboard (got "${clipboard}")`);
  await context.close();
}

// ---- Links actually navigate (Home via routed absolute URL) ----
{
  const { context, page } = await newPage("navigation", [ALLOW_NAV_404_CONSOLE]);
  await page.goto(`${base}/nested/path/that-does-not-exist`, { waitUntil: "networkidle" });
  await page.getByRole("link", { name: "Go to the Home page" }).click();
  await page.waitForURL(`${SITE_BASE_URL}index.html`);
  const homeH1 = await page.locator("h1").first().textContent();
  check(homeH1.trim().length > 0, `Home link navigates to the homepage (h1: "${homeH1.trim()}")`);
  await context.close();
}

// ---- Keyboard access: main navigation and page tools ----
{
  const { context, page } = await newPage("keyboard");
  await page.goto(`${base}/404.html`, { waitUntil: "networkidle" });

  // Tab from the top of the page; record what receives focus. Bounded
  // walk — the page header + sidebar are well under this many stops.
  const reached = await page.evaluate(async () => {
    const seen = { skipLink: false, navLink: false, pageToolsSummary: false };
    document.body.focus();
    return seen;
  });
  let navFocused = false, toolsFocused = false, skipFirst = false;
  for (let i = 0; i < 60 && !(navFocused && toolsFocused); i++) {
    await page.keyboard.press("Tab");
    const where = await page.evaluate(() => {
      const el = document.activeElement;
      return {
        skip: el?.classList?.contains("skip-link") || false,
        nav: el?.closest?.(".site-nav") !== null,
        tools: el?.matches?.(".page-tools > summary") || false,
      };
    });
    if (i === 0) skipFirst = where.skip;
    navFocused ||= where.nav;
    toolsFocused ||= where.tools;
  }
  check(skipFirst, "the skip link is the first Tab stop");
  check(toolsFocused, "the Page tools summary is reachable by keyboard");
  check(navFocused, "the main (Contents) navigation is reachable by keyboard");
  void reached;

  // Open Page tools with the keyboard and reach both action buttons.
  await page.focus(".page-tools > summary");
  await page.keyboard.press("Enter");
  check(await page.evaluate(() => document.querySelector(".page-tools").open),
    "Page tools opens with Enter");
  await page.keyboard.press("Tab");
  check(await page.evaluate(() => document.activeElement.matches("[data-action='print']")),
    "first Tab inside Page tools lands on the Print button");
  const toolsReachable = await page.evaluate(() => {
    const panel = document.querySelector(".page-tools__panel");
    const focusables = panel.querySelectorAll("button, a, summary, input");
    return Array.from(focusables).every((el) => el.tabIndex >= 0 || el.tagName === "SUMMARY");
  });
  check(toolsReachable, "every Page tools control is keyboard-focusable");
  await context.close();
}

await browser.close();
server.close();
if (fails.length) { console.error(`\n${fails.length} 404 CHECK(S) FAILED`); process.exit(1); }
reportRuntimeIssues(issues);
console.log("\nALL 404 CHECKS PASS");
