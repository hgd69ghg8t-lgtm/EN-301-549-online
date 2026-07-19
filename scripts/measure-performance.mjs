#!/usr/bin/env node
// Reproducible performance baseline / regression measurement for the
// generated site. Loads representative pages in headless Chromium against
// the same local static server the other browser suites use, and records
// per-resource decoded byte sizes and request counts, plus the request
// behaviour of the header search box and the full search page.
//
// Local measurement measures RESOURCE COUNTS and SIZES reliably; it does
// NOT model real mobile-network latency or bandwidth. Timings
// (DOMContentLoaded/load) are reported for relative before/after
// comparison only — never as absolute performance claims. Transfer bytes
// are reported two ways: decoded bytes as the browser received them from
// the (uncompressed) local server, and the gzip size of each file on
// disk as a proxy for what a production host (GitHub Pages / Cloudflare,
// which serve gzip/brotli) would transfer.
//
// Usage:
//   node scripts/measure-performance.mjs            # human summary
//   node scripts/measure-performance.mjs --json     # machine-readable
import { gzipSync } from "node:zlib";
import { readFileSync } from "node:fs";
import path from "node:path";
import {
  DOCS_DIR, startServer, launchBrowser, routeSiteBaseUrl, SITE_BASE_URL,
} from "./browser-test-lib.mjs";

const PAGES = [
  "index.html",
  "about.html",
  "clause-9-web.html",
  "annex-b-functional-performance-relationship.html",
  "search.html",
  "404.html",
];

function categorise(url) {
  const clean = url.split("?")[0].split("#")[0];
  if (/\.html$/.test(clean) || clean.endsWith("/")) return "html";
  if (/\.css$/.test(clean)) return "css";
  if (/\.m?js$/.test(clean)) return "js";
  if (/\.woff2?$/.test(clean)) return "font";
  if (/search-suggestions\.json$/.test(clean)) return "suggestIndex";
  if (/search-index\.json$/.test(clean)) return "fullIndex";
  if (/\.json$/.test(clean)) return "json";
  if (/\.(png|svg|jpg|jpeg|gif|webp|ico)$/.test(clean)) return "image";
  if (/\.pdf$/.test(clean)) return "pdf";
  return "other";
}

// gzip size on disk (production-transfer proxy) for a same-origin URL.
function diskGzip(url) {
  try {
    let rel = url;
    if (url.startsWith(SITE_BASE_URL)) rel = url.slice(SITE_BASE_URL.length);
    else rel = new URL(url).pathname.replace(/^\//, "");
    rel = decodeURIComponent(rel.split("?")[0].split("#")[0]) || "index.html";
    return gzipSync(readFileSync(path.join(DOCS_DIR, rel))).length;
  } catch {
    return null;
  }
}

async function measurePage(browser, base, page404, pageName) {
  const context = await browser.newContext();
  if (page404) await routeSiteBaseUrl(context);
  const page = await context.newPage();
  const resources = [];
  page.on("response", async (response) => {
    const req = response.request();
    const url = response.url();
    if (!url.startsWith("http://127.0.0.1:") && !url.startsWith(SITE_BASE_URL)) return;
    let decoded = null;
    try { decoded = (await response.body()).length; } catch { /* redirect/cached */ }
    resources.push({
      url, type: categorise(url), resourceType: req.resourceType(),
      status: response.status(), decoded, gzip: diskGzip(url),
    });
  });

  const target = page404 ? `${base}/does-not-exist-${Date.now()}` : `${base}/${pageName}`;
  await page.goto(target, { waitUntil: "networkidle", timeout: 30000 });
  const timing = await page.evaluate(() => {
    const n = performance.getEntriesByType("navigation")[0] || {};
    let cls = 0;
    for (const e of performance.getEntriesByType("layout-shift") || []) {
      if (!e.hadRecentInput) cls += e.value;
    }
    return {
      domContentLoaded: Math.round(n.domContentLoadedEventEnd || 0),
      load: Math.round(n.loadEventEnd || 0),
      cls: Number(cls.toFixed(4)),
    };
  });
  await context.close();

  const byType = {};
  for (const r of resources) {
    const t = byType[r.type] || (byType[r.type] = { count: 0, decoded: 0, gzip: 0 });
    t.count += 1;
    t.decoded += r.decoded || 0;
    t.gzip += r.gzip || 0;
  }
  const nonHtml = resources.filter((r) => r.type !== "html");
  return {
    page: pageName,
    requests: resources.length,
    requestsExclHtml: nonHtml.length,
    totalDecoded: resources.reduce((s, r) => s + (r.decoded || 0), 0),
    totalGzip: resources.reduce((s, r) => s + (r.gzip || 0), 0),
    byType,
    timing,
    resources: resources.map((r) => ({ url: r.url.replace(base, "").replace(SITE_BASE_URL, "/"), type: r.type, status: r.status, decoded: r.decoded, gzip: r.gzip })),
  };
}

// Requests triggered by typing into the header search box (suggestions).
async function measureHeaderSearch(browser, base) {
  const context = await browser.newContext();
  const page = await context.newPage();
  const fetched = [];
  page.on("request", (r) => {
    const t = categorise(r.url());
    if (t === "suggestIndex" || t === "fullIndex") fetched.push(t);
  });
  await page.goto(`${base}/clause-9-web.html`, { waitUntil: "networkidle" });
  await page.locator(".site-search input").click();
  await page.keyboard.type("web");
  await page.waitForTimeout(600);
  await context.close();
  return { fetched };
}

async function measureFullSearch(browser, base) {
  const context = await browser.newContext();
  const page = await context.newPage();
  const fetched = [];
  page.on("request", (r) => {
    const t = categorise(r.url());
    if (t === "suggestIndex" || t === "fullIndex") fetched.push(t);
  });
  await page.goto(`${base}/search.html?q=web`, { waitUntil: "networkidle" });
  await page.waitForTimeout(600);
  await context.close();
  return { fetched };
}

async function main() {
  const server = await startServer();
  const port = server.address().port;
  const base = `http://127.0.0.1:${port}`;
  const browser = await launchBrowser();

  const results = [];
  for (const pageName of PAGES) {
    results.push(await measurePage(browser, base, pageName === "404.html", pageName));
  }
  const headerSearch = await measureHeaderSearch(browser, base);
  const fullSearch = await measureFullSearch(browser, base);

  await browser.close();
  server.close();

  const report = { generatedBy: "scripts/measure-performance.mjs", pages: results, headerSearch, fullSearch };

  if (process.argv.includes("--json")) {
    console.log(JSON.stringify(report, null, 2));
    return;
  }

  const kb = (b) => (b / 1024).toFixed(1);
  for (const r of results) {
    console.log(`\n## ${r.page}`);
    console.log(`   requests: ${r.requests} (excl. HTML: ${r.requestsExclHtml})`);
    console.log(`   total decoded: ${kb(r.totalDecoded)} KB | total gzip(disk): ${kb(r.totalGzip)} KB`);
    for (const [type, t] of Object.entries(r.byType).sort()) {
      console.log(`     ${type.padEnd(12)} ${String(t.count).padStart(2)}×  decoded ${kb(t.decoded).padStart(8)} KB  gzip ${kb(t.gzip).padStart(8)} KB`);
    }
    console.log(`   DCL ${r.timing.domContentLoaded}ms  load ${r.timing.load}ms  CLS ${r.timing.cls}`);
  }
  console.log(`\n## Header search (type "web" on a clause page)`);
  console.log(`   index fetches: ${headerSearch.fetched.join(", ") || "none"}`);
  console.log(`## Full search (search.html?q=web)`);
  console.log(`   index fetches: ${fullSearch.fetched.join(", ") || "none"}`);
}

main().catch((err) => { console.error(err); process.exit(1); });
