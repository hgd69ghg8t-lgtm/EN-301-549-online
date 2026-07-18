// Shared infrastructure for the Playwright browser suites (a11y, layout,
// search, theme, 404): one static file server, one Chromium launcher and
// one runtime-failure tracker, so every suite exercises the same
// hosting-like behaviour and fails on the same classes of runtime error.
import { chromium } from "playwright";
import { createServer } from "node:http";
import { readFile, readFileSync } from "node:fs";
import { readFile as readFileAsync } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import path from "node:path";

export const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
export const DOCS_DIR = path.join(ROOT, "docs");

// The production base URL from the committed site configuration — the
// generated 404 page's links and assets are absolute under it.
export const SITE_BASE_URL = JSON.parse(
  readFileSync(path.join(ROOT, "data", "site-config.json"), "utf8")
).baseUrl;

export const MIME = {
  ".html": "text/html",
  ".css": "text/css",
  ".js": "text/javascript",
  ".json": "application/json",
  ".svg": "image/svg+xml",
  ".png": "image/png",
  ".woff2": "font/woff2",
  ".pdf": "application/pdf",
  ".xml": "application/xml",
  ".txt": "text/plain",
};

export function mimeFor(filePath) {
  return MIME[path.extname(filePath)] || "application/octet-stream";
}

// Serves docs/ the way static hosting (GitHub Pages / Cloudflare Pages)
// does: "/" maps to index.html, and a missing path returns the
// generated custom 404 page WITH HTTP status 404 — so suites can
// exercise the 404 page through a real missing URL, not only by
// requesting /404.html directly.
export function startServer() {
  return new Promise((resolve) => {
    const server = createServer((req, res) => {
      const urlPath = decodeURIComponent(req.url.split("?")[0]);
      const filePath = path.join(DOCS_DIR, urlPath === "/" ? "/index.html" : urlPath);
      readFile(filePath, (err, data) => {
        if (err) {
          readFile(path.join(DOCS_DIR, "404.html"), (err404, notFound) => {
            if (err404) {
              res.writeHead(404, { "Content-Type": "text/plain" });
              res.end("Not found");
              return;
            }
            res.writeHead(404, { "Content-Type": "text/html" });
            res.end(notFound);
          });
          return;
        }
        res.writeHead(200, { "Content-Type": mimeFor(filePath) });
        res.end(data);
      });
    });
    server.listen(0, "127.0.0.1", () => resolve(server));
  });
}

// PLAYWRIGHT_CHROMIUM_PATH lets a local/CI environment point at an
// already-installed Chromium binary instead of the one Playwright's own
// browser manager would download. Unset by default — normal usage is
// `npx playwright install --with-deps chromium` and a plain launch().
export function launchBrowser() {
  const launchOptions = process.env.PLAYWRIGHT_CHROMIUM_PATH
    ? { executablePath: process.env.PLAYWRIGHT_CHROMIUM_PATH }
    : {};
  return chromium.launch(launchOptions);
}

// Locally nothing serves the production origin, so tests of the 404 page
// route its absolute-URL requests to the same docs/ tree the local
// server uses — closely representing static hosting with no network
// access. Missing files get a 404 status, so the runtime tracker still
// catches a broken absolute asset link.
export async function routeSiteBaseUrl(context) {
  await context.route(`${SITE_BASE_URL}**`, async (route) => {
    const url = route.request().url();
    const rel = decodeURIComponent(url.slice(SITE_BASE_URL.length).split("#")[0].split("?")[0]);
    const filePath = path.join(DOCS_DIR, rel === "" ? "index.html" : rel);
    try {
      const body = await readFileAsync(filePath);
      await route.fulfill({ status: 200, contentType: mimeFor(filePath), body });
    } catch {
      await route.fulfill({ status: 404, contentType: "text/plain", body: "Not found" });
    }
  });
}

function isSameSite(url) {
  return url.startsWith("http://127.0.0.1:") || url.startsWith(SITE_BASE_URL);
}

// Attaches runtime-failure tracking to a page and appends findings to
// `issues` (an array shared across the suite). A suite fails on any
// unexpected:
//   - pageerror (uncaught exceptions AND unhandled promise rejections —
//     Playwright reports both through this event),
//   - console message of type "error",
//   - failed same-origin request,
//   - same-origin response with status >= 400.
// `allow` lists the narrow documented exceptions as predicate functions
// ({ kind, test }) — nothing is suppressed globally.
//
// One built-in exception: requests aborted by the browser because the
// test navigated away mid-flight (net::ERR_ABORTED). Those are
// browser-generated artefacts of test pacing, not site failures — a
// genuinely unreachable resource surfaces as a 404 response or a
// different failure code instead.
export function trackRuntimeIssues(page, issues, { label = "", allow = [] } = {}) {
  const allowed = (kind, detail) =>
    allow.some((rule) => rule.kind === kind && rule.test(detail));
  const tag = label ? `[${label}] ` : "";
  page.on("pageerror", (err) => {
    if (!allowed("pageerror", String(err))) issues.push(`${tag}pageerror: ${err}`);
  });
  page.on("console", (msg) => {
    if (msg.type() === "error" && !allowed("console", msg.text())) {
      issues.push(`${tag}console error: ${msg.text()}`);
    }
  });
  page.on("requestfailed", (request) => {
    const url = request.url();
    if (!isSameSite(url)) return;
    const errorText = request.failure()?.errorText || "unknown failure";
    if (errorText === "net::ERR_ABORTED") return; // navigation abort, see above
    if (!allowed("requestfailed", url)) {
      issues.push(`${tag}request failed: ${url} (${errorText})`);
    }
  });
  page.on("response", (response) => {
    const url = response.url();
    if (!isSameSite(url)) return;
    if (response.status() >= 400 && !allowed("response", { url, status: response.status() })) {
      issues.push(`${tag}HTTP ${response.status()}: ${url}`);
    }
  });
}

// Fails the process if any runtime issues were recorded. Call once at
// the end of a suite, after closing the browser.
export function reportRuntimeIssues(issues) {
  if (!issues.length) {
    console.log("Runtime checks OK: no page errors, console errors, or failed same-origin requests.");
    return;
  }
  console.error(`\n${issues.length} runtime issue(s):\n`);
  for (const issue of issues) console.error(`  FAIL ${issue}`);
  process.exit(1);
}
