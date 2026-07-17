#!/usr/bin/env node
// Performance measurement and budget enforcement for the generated site.
//
// Everything is measured against the LOCAL generated docs/ directory over
// a loopback HTTP server — never against the public internet — so results
// are reproducible and CI never fails on someone else's network weather.
//
// Two modes:
//   node scripts/check-performance.mjs            measure and print a report
//   node scripts/check-performance.mjs --check    also compare against the
//                                                 budgets in
//                                                 data/performance-budgets.json
//                                                 and exit non-zero on breach
//   ... --json <file>                             additionally write the raw
//                                                 measurements as JSON
//
// Measurement profile: a mobile viewport with CPU and network throttling
// applied through the Chrome DevTools Protocol (a mid-range phone on a
// fast-3G-class connection), because that is the audience the site must
// stay fast for — not a desktop on localhost.
//
// Byte budgets are enforced strictly (they are deterministic); timing
// budgets carry generous tolerances because even local, throttled timings
// jitter — see data/performance-budgets.json.
import { chromium } from "playwright";
import { createServer } from "node:http";
import { readFile, readFileSync, readdirSync, statSync, writeFileSync, existsSync } from "node:fs";
import { gzipSync } from "node:zlib";
import path from "node:path";
import process from "node:process";

const ROOT = path.resolve(path.dirname(new URL(import.meta.url).pathname), "..");
const DOCS_DIR = path.join(ROOT, "docs");
const BUDGETS_PATH = path.join(ROOT, "data", "performance-budgets.json");

const PAGES = [
  "index.html",
  "clause-3-definitions.html",
  "clause-9-web.html",
  "annex-b-functional-performance-relationship.html",
  "search.html",
];

// Mid-range mobile profile: fast-3G-class network, 4x CPU slowdown.
const NETWORK = {
  offline: false,
  downloadThroughput: (1.6 * 1024 * 1024) / 8, // 1.6 Mbit/s
  uploadThroughput: (0.75 * 1024 * 1024) / 8,
  latency: 150, // ms round-trip
};
const CPU_THROTTLE = 4;
const VIEWPORT = { width: 360, height: 740 };

const MIME = {
  ".html": "text/html; charset=utf-8",
  ".css": "text/css",
  ".js": "text/javascript",
  ".mjs": "text/javascript",
  ".json": "application/json",
  ".woff2": "font/woff2",
  ".svg": "image/svg+xml",
  ".png": "image/png",
  ".pdf": "application/pdf",
  ".xml": "application/xml",
  ".txt": "text/plain",
};

function startServer() {
  return new Promise((resolve) => {
    const server = createServer((req, res) => {
      const urlPath = decodeURIComponent(req.url.split("?")[0]);
      const filePath = path.join(DOCS_DIR, urlPath === "/" ? "/index.html" : urlPath);
      readFile(filePath, (err, data) => {
        if (err) { res.writeHead(404); res.end("Not found"); return; }
        res.writeHead(200, { "Content-Type": MIME[path.extname(filePath)] || "application/octet-stream" });
        res.end(data);
      });
    });
    server.listen(0, "127.0.0.1", () => resolve(server));
  });
}

// ---------------------------------------------------------------------
// Static size report: every production CSS/JS/font/JSON/HTML file, with
// raw and gzipped sizes (gzip approximates what a compressing host
// actually transfers; GitHub Pages serves gzip).
// ---------------------------------------------------------------------

function walk(dir) {
  const out = [];
  for (const entry of readdirSync(dir, { withFileTypes: true })) {
    const p = path.join(dir, entry.name);
    if (entry.isDirectory()) out.push(...walk(p));
    else out.push(p);
  }
  return out;
}

function staticSizes() {
  const byExt = { css: [], js: [], font: [], json: [], html: [] };
  for (const file of walk(DOCS_DIR)) {
    const rel = path.relative(DOCS_DIR, file);
    if (rel.startsWith("source" + path.sep)) continue; // the committed source PDF
    const ext = path.extname(file);
    const kind = ext === ".css" ? "css"
      : ext === ".js" ? "js"
      : ext === ".woff2" ? "font"
      : ext === ".json" ? "json"
      : ext === ".html" ? "html"
      : null;
    if (!kind) continue;
    const raw = readFileSync(file);
    byExt[kind].push({ file: rel, bytes: raw.length, gzipBytes: gzipSync(raw, { level: 9 }).length });
  }
  for (const kind of Object.keys(byExt)) byExt[kind].sort((a, b) => b.bytes - a.bytes);
  return byExt;
}

// ---------------------------------------------------------------------
// Per-page browser measurement
// ---------------------------------------------------------------------

const OBSERVER_INIT = `
  window.__perf = { lcp: 0, cls: 0, fcp: 0, longTasks: [] };
  try {
    new PerformanceObserver((list) => {
      for (const e of list.getEntries()) window.__perf.lcp = Math.max(window.__perf.lcp, e.startTime);
    }).observe({ type: "largest-contentful-paint", buffered: true });
  } catch (e) {}
  try {
    new PerformanceObserver((list) => {
      for (const e of list.getEntries()) if (!e.hadRecentInput) window.__perf.cls += e.value;
    }).observe({ type: "layout-shift", buffered: true });
  } catch (e) {}
  try {
    new PerformanceObserver((list) => {
      for (const e of list.getEntries()) if (e.name === "first-contentful-paint") window.__perf.fcp = e.startTime;
    }).observe({ type: "paint", buffered: true });
  } catch (e) {}
  try {
    new PerformanceObserver((list) => {
      for (const e of list.getEntries()) window.__perf.longTasks.push(Math.round(e.duration));
    }).observe({ type: "longtask", buffered: true });
  } catch (e) {}
`;

function classify(url) {
  const p = new URL(url).pathname;
  if (p.endsWith(".css")) return "css";
  if (p.endsWith(".js")) return "js";
  if (p.endsWith(".woff2")) return "font";
  if (p.endsWith(".json")) return "json";
  if (p.endsWith(".html") || p === "/" || !path.extname(p)) return "html";
  return "other";
}

async function measurePage(browser, origin, pagePath) {
  const context = await browser.newContext({ viewport: VIEWPORT, isMobile: true, hasTouch: true });
  const page = await context.newPage();
  await page.addInitScript(OBSERVER_INIT);
  const client = await context.newCDPSession(page);
  await client.send("Network.enable");
  await client.send("Network.emulateNetworkConditions", NETWORK);
  await client.send("Emulation.setCPUThrottlingRate", { rate: CPU_THROTTLE });
  await client.send("Performance.enable");

  const transfers = { html: 0, css: 0, js: 0, font: 0, json: 0, other: 0 };
  let requests = 0;
  page.on("response", async (response) => {
    requests += 1;
    try {
      const body = await response.body();
      transfers[classify(response.url())] += body.length;
    } catch (e) { /* navigation-cancelled bodies are fine to skip */ }
  });

  await page.goto(`${origin}/${pagePath}`, { waitUntil: "load" });
  // let LCP/CLS/longtask observers settle after load
  await page.waitForTimeout(1200);

  const timing = await page.evaluate(() => {
    const nav = performance.getEntriesByType("navigation")[0];
    return {
      domContentLoaded: Math.round(nav.domContentLoadedEventEnd),
      load: Math.round(nav.loadEventEnd),
      fcp: Math.round(window.__perf.fcp),
      lcp: Math.round(window.__perf.lcp),
      cls: Number(window.__perf.cls.toFixed(4)),
      longTasks: window.__perf.longTasks,
      domNodes: document.getElementsByTagName("*").length,
    };
  });
  const metrics = (await client.send("Performance.getMetrics")).metrics;
  const metric = (name) => {
    const m = metrics.find((x) => x.name === name);
    return m ? m.value : 0;
  };

  const result = {
    page: pagePath,
    requests,
    transfers,
    ...timing,
    scriptDurationMs: Math.round(metric("ScriptDuration") * 1000),
    layoutDurationMs: Math.round(metric("LayoutDuration") * 1000),
    blockedMs: timing.longTasks.reduce((a, d) => a + Math.max(0, d - 50), 0),
  };

  // Search responsiveness: time from typing a query to results rendered.
  if (pagePath === "search.html") {
    result.searchResponseMs = await page.evaluate(async () => {
      const input = document.getElementById("search-input");
      const results = document.getElementById("search-results");
      const t0 = performance.now();
      input.value = "keyboard accessibility";
      // Re-dispatch while waiting: on a throttled connection the page's
      // input listener may not exist yet while the index downloads, and a
      // real user's later keystrokes land after it attaches.
      await new Promise((resolve, reject) => {
        const deadline = performance.now() + 30000;
        (function poll() {
          if (results.children.length > 0) return resolve();
          if (performance.now() > deadline) return reject(new Error("search never rendered results"));
          input.dispatchEvent(new Event("input", { bubbles: true }));
          // slower than the page's own input debounce, so the debounce
          // timer actually gets to fire between dispatches
          setTimeout(poll, 400);
        })();
      });
      return Math.round(performance.now() - t0);
    });
  }

  await context.close();
  return result;
}

// ---------------------------------------------------------------------
// Budget comparison
// ---------------------------------------------------------------------

function kb(n) { return `${(n / 1024).toFixed(1)} KB`; }

function checkBudgets(measurements, budgets) {
  const failures = [];
  const fail = (msg) => failures.push(msg);
  const sizes = measurements.staticSizes;
  const sum = (list) => list.reduce((a, f) => a + f.bytes, 0);

  const totalCss = sum(sizes.css);
  const totalFonts = sum(sizes.font);
  const largestHtml = sizes.html[0] || { file: "(none)", bytes: 0 };
  const coreJs = sizes.js.find((f) => /(^|\/)core\.[0-9a-f]+\.js$/.test(f.file) || f.file.endsWith("site.js"));
  const suggestIndex = sizes.json.find((f) => /search-suggestions\./.test(f.file));
  const fullIndex = sizes.json.find((f) => /search-index/.test(f.file));

  const sizeChecks = [
    ["totalCssBytes", totalCss, "total production CSS"],
    ["coreJsBytes", coreJs ? coreJs.bytes : 0, `core JavaScript (${coreJs ? coreJs.file : "missing"})`],
    ["totalJsBytes", sum(sizes.js), "total production JavaScript"],
    ["fontBytes", totalFonts, "production fonts"],
    ["largestHtmlBytes", largestHtml.bytes, `largest HTML page (${largestHtml.file})`],
    ["suggestionsIndexBytes", suggestIndex ? suggestIndex.bytes : 0, "suggestions index"],
    ["fullSearchIndexBytes", fullIndex ? fullIndex.bytes : 0, "full search index"],
  ];
  for (const [key, actual, label] of sizeChecks) {
    if (budgets[key] !== undefined && actual > budgets[key]) {
      fail(`FAIL: ${label} is ${kb(actual)}; budget is ${kb(budgets[key])}.`);
    }
  }

  for (const m of measurements.pages) {
    const initialTransfer = Object.values(m.transfers).reduce((a, b) => a + b, 0);
    const perPage = [
      ["maxInitialRequests", m.requests, (v, b) => `FAIL: ${m.page} made ${v} initial requests; budget is ${b}.`],
      ["maxInitialTransferBytes", initialTransfer, (v, b) => `FAIL: ${m.page} transferred ${kb(v)} on first load; budget is ${kb(b)}.`],
      ["maxDomNodes", m.domNodes, (v, b) => `FAIL: ${m.page} has ${v} DOM nodes; budget is ${b}.`],
      ["maxCls", m.cls, (v, b) => `FAIL: ${m.page} cumulative layout shift is ${v}; budget is ${b}.`],
      ["maxScriptDurationMs", m.scriptDurationMs, (v, b) => `FAIL: ${m.page} spent ${v} ms evaluating JavaScript; budget is ${b} ms.`],
      ["maxLongTasks", m.longTasks.length, (v, b) => `FAIL: ${m.page} had ${v} long tasks (${m.longTasks.join(", ")} ms); budget is ${b}.`],
    ];
    for (const [key, actual, message] of perPage) {
      if (budgets[key] !== undefined && actual > budgets[key]) fail(message(actual, budgets[key]));
    }
    if (m.page !== "search.html" && budgets.forbidFullIndexOnOrdinaryPages && m.transfers.json > 0) {
      fail(`FAIL: ${m.page} downloaded ${kb(m.transfers.json)} of JSON during ordinary page load; ordinary pages must not fetch search indexes.`);
    }
    if (budgets.fontBytes === 0 && m.transfers.font > 0) {
      fail(`FAIL: ${m.page} downloaded ${kb(m.transfers.font)} of webfonts; the production budget is zero font requests.`);
    }
    if (m.searchResponseMs !== undefined && budgets.maxSearchResponseMs !== undefined
        && m.searchResponseMs > budgets.maxSearchResponseMs) {
      fail(`FAIL: search took ${m.searchResponseMs} ms from typing to rendered results; budget is ${budgets.maxSearchResponseMs} ms.`);
    }
  }
  return failures;
}

// ---------------------------------------------------------------------

const args = process.argv.slice(2);
const doCheck = args.includes("--check");
const jsonAt = args.indexOf("--json");
const jsonPath = jsonAt !== -1 ? args[jsonAt + 1] : null;

const server = await startServer();
const origin = `http://127.0.0.1:${server.address().port}`;
const browser = await chromium.launch({ executablePath: process.env.PLAYWRIGHT_CHROMIUM_PATH });

const measurements = { profile: { network: NETWORK, cpuThrottle: CPU_THROTTLE, viewport: VIEWPORT }, pages: [], staticSizes: staticSizes() };
for (const pagePath of PAGES) {
  process.stderr.write(`measuring ${pagePath}...\n`);
  measurements.pages.push(await measurePage(browser, origin, pagePath));
}
await browser.close();
server.close();

// ---- report ----
console.log("\n== Static production asset sizes (raw / gzip) ==");
for (const kind of ["css", "js", "font", "json"]) {
  for (const f of measurements.staticSizes[kind]) {
    console.log(`  ${kind.padEnd(4)} ${f.file.padEnd(46)} ${kb(f.bytes).padStart(10)} / ${kb(f.gzipBytes)}`);
  }
}
const htmlFiles = measurements.staticSizes.html;
const htmlTotal = htmlFiles.reduce((a, f) => a + f.bytes, 0);
console.log(`  html ${htmlFiles.length} pages, total ${kb(htmlTotal)}, largest ${htmlFiles[0].file} ${kb(htmlFiles[0].bytes)} / ${kb(htmlFiles[0].gzipBytes)}`);

console.log("\n== Page measurements (mobile viewport, fast-3G-class network, 4x CPU) ==");
for (const m of measurements.pages) {
  console.log(`  ${m.page}`);
  console.log(`    requests ${m.requests}  transfer html ${kb(m.transfers.html)} css ${kb(m.transfers.css)} js ${kb(m.transfers.js)} font ${kb(m.transfers.font)} json ${kb(m.transfers.json)}`);
  console.log(`    DCL ${m.domContentLoaded} ms  load ${m.load} ms  FCP ${m.fcp} ms  LCP ${m.lcp} ms  CLS ${m.cls}`);
  console.log(`    script ${m.scriptDurationMs} ms  layout ${m.layoutDurationMs} ms  long tasks [${m.longTasks.join(", ")}]  DOM nodes ${m.domNodes}`);
  if (m.searchResponseMs !== undefined) console.log(`    search type-to-results ${m.searchResponseMs} ms`);
}

if (jsonPath) writeFileSync(jsonPath, JSON.stringify(measurements, null, 2) + "\n");

if (doCheck) {
  if (!existsSync(BUDGETS_PATH)) {
    console.error(`No budgets file at ${BUDGETS_PATH}`);
    process.exit(1);
  }
  const budgets = JSON.parse(readFileSync(BUDGETS_PATH, "utf8")).budgets;
  const failures = checkBudgets(measurements, budgets);
  if (failures.length) {
    console.error("\n== Performance budget failures ==");
    for (const f of failures) console.error(f);
    process.exit(1);
  }
  console.log("\nALL PERFORMANCE BUDGETS PASS");
}
