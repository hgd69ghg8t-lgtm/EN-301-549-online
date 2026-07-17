// Shared plumbing for the Playwright suites: the local docs/ server and
// runtime-error tracking.
//
// Runtime-error tracking is the reason this file exists: every suite
// attaches trackRuntimeErrors() to every page it opens, so an unexpected
// JavaScript exception, unhandled promise rejection (surfaced by
// Playwright as a pageerror), console error, or failed/4xx same-origin
// request fails the suite — not just the specific behaviour a test was
// looking at. Tests that deliberately break a resource (the module-
// failure suite) pass allowUrls patterns for exactly the requests they
// broke; everything else stays fatal.
import { createServer } from "node:http";
import { readFile } from "node:fs";
import path from "node:path";

export const DOCS_DIR = path.resolve("docs");

const MIME = {
  ".html": "text/html; charset=utf-8",
  ".css": "text/css",
  ".js": "text/javascript",
  ".json": "application/json",
  ".woff2": "font/woff2",
  ".svg": "image/svg+xml",
  ".png": "image/png",
  ".pdf": "application/pdf",
  ".xml": "application/xml",
  ".txt": "text/plain",
};

export function startDocsServer() {
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

// Console messages that are genuinely benign and outside the site's
// control. Currently empty on purpose: the site's own pages must log
// nothing. Add entries only with a comment explaining the browser
// behaviour that makes the message unavoidable.
const BENIGN_CONSOLE = [
];

function allowed(text, patterns) {
  return patterns.some((p) => (p instanceof RegExp ? p.test(text) : text.includes(p)));
}

/**
 * Attach exhaustive runtime-problem tracking to a page. Returns the
 * (live) array of problem strings; call assertNoRuntimeErrors() at the
 * end of the suite.
 *
 * options.allowUrls: RegExp/substring patterns for request URLs a test
 * deliberately broke (their failures/4xx are expected, not fatal).
 */
export function trackRuntimeErrors(page, options = {}) {
  const allowUrls = options.allowUrls || [];
  const problems = options.sink || [];
  const label = () => {
    try { return page.url(); } catch { return "(page)"; }
  };
  // Uncaught exceptions AND unhandled promise rejections both arrive here.
  page.on("pageerror", (err) => {
    // Errors on about:blank come from harness init scripts (which run on
    // the initial blank document too, where e.g. localStorage is denied)
    // — site code never executes there.
    if (label() === "about:blank") return;
    problems.push(`pageerror on ${label()}: ${err.message}`);
  });
  page.on("console", (msg) => {
    if (msg.type() !== "error") return;
    const text = msg.text();
    if (allowed(text, BENIGN_CONSOLE)) return;
    // Console errors for requests the test broke on purpose ("Failed to
    // load resource...") carry the URL in msg.location().
    const url = (msg.location() && msg.location().url) || "";
    if (allowUrls.length && (allowed(url, allowUrls) || allowed(text, allowUrls))) return;
    problems.push(`console.error on ${label()}: ${text}`);
  });
  page.on("requestfailed", (req) => {
    const failure = req.failure() ? req.failure().errorText : "failed";
    if (failure === "net::ERR_ABORTED" && !allowUrls.length) {
      // Navigating away mid-load aborts subresource requests; that's the
      // test moving on, not the site failing.
      return;
    }
    if (allowed(req.url(), allowUrls)) return;
    if (failure === "net::ERR_ABORTED") return;
    problems.push(`request failed on ${label()}: ${req.url()} (${failure})`);
  });
  page.on("response", (res) => {
    if (res.status() < 400) return;
    if (allowed(res.url(), allowUrls)) return;
    problems.push(`HTTP ${res.status()} on ${label()}: ${res.url()}`);
  });
  return problems;
}

export function assertNoRuntimeErrors(problems, failures) {
  if (!problems.length) return;
  console.error(`\n${problems.length} unexpected runtime problem(s):`);
  for (const p of problems) console.error(`  ${p}`);
  failures.push(`${problems.length} unexpected runtime problem(s) — see above`);
}

/**
 * Track runtime problems on every page of every context the browser
 * creates from now on, without touching each call site. Returns the
 * shared problems array; check it (assertNoRuntimeErrors or manually)
 * before deciding the suite's exit code.
 */
export function trackAllPages(browser, options = {}) {
  const problems = [];
  const origNewContext = browser.newContext.bind(browser);
  browser.newContext = async (...args) => {
    const context = await origNewContext(...args);
    context.on("page", (page) => trackRuntimeErrors(page, { ...options, sink: problems }));
    return context;
  };
  return problems;
}

export function chromiumLaunchOptions() {
  // PLAYWRIGHT_CHROMIUM_PATH lets a local/CI environment point at an
  // already-installed Chromium binary instead of the one Playwright's
  // own browser manager would download.
  return process.env.PLAYWRIGHT_CHROMIUM_PATH
    ? { executablePath: process.env.PLAYWRIGHT_CHROMIUM_PATH }
    : {};
}
