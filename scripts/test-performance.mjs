#!/usr/bin/env node
// Deterministic performance budgets for the generated site. Loads
// representative pages in headless Chromium against the same local static
// server the other suites use and asserts the REQUEST GRAPH (which
// resources each page loads) and RESOURCE SIZES (bytes on disk) — never
// wall-clock timings, which vary too much on hosted runners to be a
// stable budget. Fails with an actionable message on any regression.
//
// Thresholds are evidence-based (see docs-for-maintainers/performance.md)
// with margin so an incidental change doesn't cause CI churn. Run against
// a clean build:  npm run build && npm run test:performance
import { readFileSync, readdirSync } from "node:fs";
import path from "node:path";
import {
  DOCS_DIR, startServer, launchBrowser, routeSiteBaseUrl,
  trackRuntimeIssues, reportRuntimeIssues, SITE_BASE_URL,
} from "./browser-test-lib.mjs";

// --- Budgets (bytes / counts). Adjust with evidence when the deliberate
// design changes, not to paper over an accidental regression.
const BUDGETS = {
  homepageRequestsExclHtml: 5,   // css + main.js + favicon, with head-room
  clauseRequestsExclHtml: 6,     // + tables.js
  mainJsMaxBytes: 24 * 1024,     // shared bundle on every page (~18 KB now)
  suggestIndexMaxBytes: 160 * 1024,   // header-box index (~129 KB now)
  fullIndexMaxBytes: 660 * 1024,      // full-text index, materially below
                                      // the ~738 KB pre-split baseline
  cssMaxBytes: 40 * 1024,        // minified stylesheet (~32 KB now)
};

const fails = [];
const issues = [];
const check = (ok, msg) => { console.log((ok ? "ok   " : "FAIL ") + msg); if (!ok) fails.push(msg); };

function fileBytes(rel) {
  return readFileSync(path.join(DOCS_DIR, rel)).length;
}
function only(dir, pattern) {
  const hits = readdirSync(path.join(DOCS_DIR, dir)).filter((f) => pattern.test(f));
  if (hits.length !== 1) throw new Error(`expected exactly one ${pattern} in ${dir}, found ${hits}`);
  return path.join(dir, hits[0]);
}

function categorise(url) {
  const clean = url.split("?")[0].split("#")[0];
  if (/\.html$/.test(clean) || clean.endsWith("/")) return "html";
  if (/\.css$/.test(clean)) return "css";
  if (/\.m?js$/.test(clean)) return "js";
  if (/\.woff2?$/.test(clean)) return "font";
  if (/search-suggestions\.json$/.test(clean)) return "suggestIndex";
  if (/search-index\.json$/.test(clean)) return "fullIndex";
  return "other";
}

async function loadResources(browser, base, pageName, { is404 = false } = {}) {
  const context = await browser.newContext();
  if (is404) await routeSiteBaseUrl(context);
  const page = await context.newPage();
  trackRuntimeIssues(page, issues, {
    label: pageName,
    allow: is404 ? [{ kind: "console", test: (t) => /Failed to load resource.*404/i.test(t) },
                    { kind: "response", test: ({ status }) => status === 404 }] : [],
  });
  const seen = [];
  page.on("response", (r) => {
    const url = r.url();
    if (url.startsWith("http://127.0.0.1:") || url.startsWith(SITE_BASE_URL)) {
      seen.push({ url, type: categorise(url) });
    }
  });
  const target = is404 ? `${base}/missing-${Date.now()}` : `${base}/${pageName}`;
  await page.goto(target, { waitUntil: "networkidle", timeout: 30000 });
  await context.close();
  return seen;
}

async function main() {
  const server = await startServer();
  const port = server.address().port;
  const base = `http://127.0.0.1:${port}`;
  const browser = await launchBrowser();

  // --- On-disk asset-size budgets (deterministic)
  const mainJs = only("assets/js", /^main\.[0-9a-f]{8}\.js$/);
  const css = only("assets/css", /^style\.[0-9a-f]{8}\.css$/);
  check(fileBytes(mainJs) <= BUDGETS.mainJsMaxBytes,
    `main bundle ${(fileBytes(mainJs) / 1024).toFixed(1)} KB <= ${BUDGETS.mainJsMaxBytes / 1024} KB`);
  check(fileBytes(css) <= BUDGETS.cssMaxBytes,
    `stylesheet ${(fileBytes(css) / 1024).toFixed(1)} KB <= ${BUDGETS.cssMaxBytes / 1024} KB`);
  check(fileBytes("search-suggestions.json") <= BUDGETS.suggestIndexMaxBytes,
    `suggestion index ${(fileBytes("search-suggestions.json") / 1024).toFixed(1)} KB <= ${BUDGETS.suggestIndexMaxBytes / 1024} KB`);
  check(fileBytes("search-index.json") <= BUDGETS.fullIndexMaxBytes,
    `full index ${(fileBytes("search-index.json") / 1024).toFixed(1)} KB <= ${BUDGETS.fullIndexMaxBytes / 1024} KB`);

  // --- Per-page request-graph budgets
  const pages = {
    home: await loadResources(browser, base, "index.html"),
    clause: await loadResources(browser, base, "clause-9-web.html"),
    search: await loadResources(browser, base, "search.html"),
    notFound: await loadResources(browser, base, "404.html", { is404: true }),
  };

  const exclHtml = (rs) => rs.filter((r) => r.type !== "html");
  const has = (rs, type) => rs.some((r) => r.type === type);
  const count = (rs, type) => rs.filter((r) => r.type === type).length;

  check(exclHtml(pages.home).length <= BUDGETS.homepageRequestsExclHtml,
    `homepage ${exclHtml(pages.home).length} requests (excl. HTML) <= ${BUDGETS.homepageRequestsExclHtml}`);
  check(exclHtml(pages.clause).length <= BUDGETS.clauseRequestsExclHtml,
    `clause ${exclHtml(pages.clause).length} requests (excl. HTML) <= ${BUDGETS.clauseRequestsExclHtml}`);

  // Zero font requests, anywhere.
  for (const [name, rs] of Object.entries(pages)) {
    check(!has(rs, "font"), `${name}: zero font requests`);
  }

  // The full-text index and the search-page bundle are search.html-only.
  check(!has(pages.home, "fullIndex") && !has(pages.clause, "fullIndex"),
    "full-text index is not fetched on the homepage or a clause page");
  check(!pages.home.some((r) => /search-page\./.test(r.url)) &&
        !pages.clause.some((r) => /search-page\./.test(r.url)),
    "search-page bundle is not loaded on the homepage or a clause page");
  check(pages.search.some((r) => /search-page\./.test(r.url)),
    "search-page bundle IS loaded on search.html");

  // Tables bundle only where there are tables.
  check(!pages.home.some((r) => /tables\./.test(r.url)),
    "tables bundle is not loaded on the table-free homepage");
  check(pages.clause.some((r) => /tables\./.test(r.url)),
    "tables bundle IS loaded on a clause page with tables");

  // Exactly one CSS and no more than the expected JS bundles per page.
  check(count(pages.home, "css") === 1, "homepage loads exactly one stylesheet");
  check(count(pages.home, "js") === 1, "homepage loads exactly one JS bundle (main)");
  check(count(pages.clause, "js") === 2, "clause page loads exactly two JS bundles (main + tables)");

  await browser.close();
  server.close();

  if (fails.length) { console.error(`\n${fails.length} PERFORMANCE BUDGET(S) EXCEEDED`); process.exit(1); }
  reportRuntimeIssues(issues);
  console.log("\nALL PERFORMANCE BUDGETS OK");
}

main().catch((err) => { console.error(err); process.exit(1); });
