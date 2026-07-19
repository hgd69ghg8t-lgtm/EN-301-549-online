// Shared search machinery used by BOTH the header suggestions and the
// full search page: query tokenising, relevance scoring, the
// highlight-parameter helper, and a robust index loader. Bundled into
// the main script (the header form is on every page); the search-page
// module reuses the same helpers via window.__site.search so scoring can
// never drift between the two surfaces.
(function () {
  "use strict";

  function searchTokens(q) {
    return q.toLowerCase().split(/\s+/).filter(Boolean);
  }

  function scoreSearchEntry(entry, toks, q) {
    var t = (entry.t || "").toLowerCase();
    // Suggestion-index entries carry no body ("b"); title-only matching
    // is intended there. The full index has bodies for recall.
    var b = (entry.b || "").toLowerCase();
    var score = 0;
    for (var i = 0; i < toks.length; i++) {
      var inTitle = t.indexOf(toks[i]) !== -1;
      var inBody = b.indexOf(toks[i]) !== -1;
      if (!inTitle && !inBody) return 0; // every word must match somewhere
      score += inTitle ? 3 : 1;
    }
    // A query that looks like a clause number ("9.1.4.4") should surface
    // that exact heading first.
    if (t.indexOf(q) === 0) score += 10;
    else if (t.indexOf(q) !== -1) score += 4;
    return score;
  }

  function searchHits(index, q) {
    var toks = searchTokens(q);
    var ql = q.toLowerCase();
    var hits = [];
    for (var i = 0; i < index.length; i++) {
      var s = scoreSearchEntry(index[i], toks, ql);
      if (s > 0) hits.push({ s: s, e: index[i] });
    }
    hits.sort(function (a, b) { return b.s - a.s; });
    return hits;
  }

  // Result links carry the query as ?h=…, so the destination page can
  // highlight the matched words on arrival. Purely client-side
  // presentation — the page's markup on disk never changes.
  function withHighlightParam(u, q) {
    var hashAt = u.indexOf("#");
    var base = hashAt === -1 ? u : u.slice(0, hashAt);
    var hash = hashAt === -1 ? "" : u.slice(hashAt);
    return base + (base.indexOf("?") === -1 ? "?" : "&") + "h=" + encodeURIComponent(q) + hash;
  }

  // Robust one-array-of-objects JSON loader: rejects a non-OK response,
  // an unexpected content type, a non-array body, or entries missing a
  // required string field — so a truncated or wrong file fails loudly
  // instead of throwing deep inside rendering. requiredFields are checked
  // on a sample of entries (checking every entry of a large index would
  // be wasteful; a malformed generator shows up in the first rows).
  function loadJsonArray(url, requiredFields) {
    return fetch(url).then(function (r) {
      if (!r.ok) throw new Error("index request failed: HTTP " + r.status);
      var ct = r.headers.get("content-type") || "";
      if (ct && ct.toLowerCase().indexOf("json") === -1) {
        throw new Error("index has unexpected content-type: " + ct);
      }
      return r.json();
    }).then(function (data) {
      if (!Array.isArray(data)) throw new Error("index is not an array");
      var sample = Math.min(data.length, 20);
      for (var i = 0; i < sample; i++) {
        var entry = data[i];
        if (!entry || typeof entry !== "object") throw new Error("index entry is not an object");
        for (var f = 0; f < requiredFields.length; f++) {
          if (typeof entry[requiredFields[f]] !== "string") {
            throw new Error("index entry missing field: " + requiredFields[f]);
          }
        }
      }
      return data;
    });
  }

  // Memoised loader that retries after a failure: the resolved promise is
  // cached, but a rejected one is cleared so a later interaction can try
  // again (a transient network blip must not permanently disable search).
  function makeIndexLoader(url, requiredFields) {
    var promise = null;
    return function () {
      if (!promise) {
        promise = loadJsonArray(url, requiredFields);
        promise.catch(function () { promise = null; });
      }
      return promise;
    };
  }

  window.__site = window.__site || {};
  window.__site.search = {
    tokens: searchTokens,
    hits: searchHits,
    withHighlightParam: withHighlightParam,
    makeIndexLoader: makeIndexLoader,
  };
})();
