#!/usr/bin/env node
// Build-time asset minifier, invoked by scripts/build.py.
//
// Reads every readable source file in scripts/source/ and writes a JSON
// object { "<filename>": "<minified text>", ... } to stdout. build.py
// content-hashes each result and writes the production files under
// docs/assets/ — this script never touches docs/ itself.
//
// Minification uses mature, widely-deployed libraries only (terser for
// JavaScript, csso for CSS — both pinned via package-lock.json), with
// fixed options, so a rebuild from unchanged source is byte-identical
// and the repository's reproducible-build guarantee holds. No source
// maps are emitted: the readable source lives in scripts/source/ in the
// same repository, which serves the maintenance need with no risk of
// leaking local paths.
import { readFileSync, readdirSync } from "node:fs";
import path from "node:path";
import { minify as terserMinify } from "terser";
import { minify as cssoMinify } from "csso";

const SOURCE_DIR = path.resolve(path.dirname(new URL(import.meta.url).pathname), "source");

const out = {};
for (const name of readdirSync(SOURCE_DIR).sort()) {
  const ext = path.extname(name);
  const text = readFileSync(path.join(SOURCE_DIR, name), "utf8");
  if (ext === ".js") {
    const result = await terserMinify(text, {
      compress: { passes: 2 },
      mangle: true,
      format: { comments: false },
    });
    if (result.error) {
      console.error(`terser failed on ${name}: ${result.error}`);
      process.exit(1);
    }
    out[name] = result.code;
  } else if (ext === ".css") {
    out[name] = cssoMinify(text).css;
  }
  // anything else in scripts/source/ (e.g. a README) is not an asset
}
process.stdout.write(JSON.stringify(out));
