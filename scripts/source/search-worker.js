/*
  search-worker.js — full-text search ranking off the main thread.

  Spawned by search.js on search.html only. Protocol (all messages are
  plain objects; anything malformed is ignored rather than thrown):

    -> { type: "init",  url, bodyCut: {before, after} }
         Fetch and hold the full search index. Replies
         { type: "ready", count } or { type: "error", message }.

    -> { type: "query", id, q, limit }
         Rank the index for q. Replies { type: "results", id, q, total,
         results: [{ u, t, p, snip: {text, pre, post} }] } — only the
         top `limit` hits, each with a pre-cut snippet window, never the
         index itself, so the reply stays small no matter how large the
         index grows. Queries arriving before the index has loaded are
         answered once it has (or once loading has failed).

  NOTE: the scoring here must stay in step with the fallback in
  scripts/source/search.js — a browser without Worker support must rank
  results identically.
*/
(function () {
  "use strict";

  var index = null;
  var loadError = null;
  var loading = false;
  var bodyCut = { before: 70, after: 130 };
  var waiting = []; // queries that arrived while the index was loading

  function searchTokens(q) {
    return q.toLowerCase().split(/\s+/).filter(Boolean);
  }
  function scoreSearchEntry(entry, toks, q) {
    var t = entry.t.toLowerCase();
    var b = (entry.b || "").toLowerCase();
    var score = 0;
    for (var i = 0; i < toks.length; i++) {
      var inTitle = t.indexOf(toks[i]) !== -1;
      var inBody = b.indexOf(toks[i]) !== -1;
      if (!inTitle && !inBody) return 0;
      score += inTitle ? 3 : 1;
    }
    if (t.indexOf(q) === 0) score += 10;
    else if (t.indexOf(q) !== -1) score += 4;
    if (entry.n && entry.n === q) score += 100;
    return score;
  }

  function cutSnippet(b, toks) {
    if (!b) return { text: "", pre: false, post: false };
    var lower = b.toLowerCase();
    var pos = -1;
    for (var i = 0; i < toks.length; i++) {
      pos = lower.indexOf(toks[i]);
      if (pos !== -1) break;
    }
    if (pos === -1) pos = 0;
    var start = Math.max(0, pos - bodyCut.before);
    var end = Math.min(b.length, pos + bodyCut.after);
    return { text: b.slice(start, end), pre: start > 0, post: end < b.length };
  }

  function answer(msg) {
    if (loadError) {
      self.postMessage({ type: "error", message: loadError });
      return;
    }
    var q = msg.q;
    var toks = searchTokens(q);
    var ql = q.toLowerCase();
    var limit = typeof msg.limit === "number" && msg.limit > 0 ? msg.limit : 50;
    var hits = [];
    for (var i = 0; i < index.length; i++) {
      var s = scoreSearchEntry(index[i], toks, ql);
      if (s > 0) hits.push({ s: s, e: index[i] });
    }
    hits.sort(function (a, b) { return b.s - a.s; });
    var results = hits.slice(0, limit).map(function (hit) {
      return { u: hit.e.u, t: hit.e.t, p: hit.e.p, snip: cutSnippet(hit.e.b || "", toks) };
    });
    self.postMessage({ type: "results", id: msg.id, q: q, total: hits.length, results: results });
  }

  function load(url) {
    loading = true;
    fetch(url).then(function (response) {
      if (!response.ok) {
        throw new Error("HTTP " + response.status + " loading " + url);
      }
      return response.json();
    }).then(function (data) {
      if (!Array.isArray(data)) {
        throw new Error("search index is not a JSON array");
      }
      index = data;
      self.postMessage({ type: "ready", count: index.length });
      waiting.splice(0).forEach(answer);
    }).catch(function (err) {
      loadError = String((err && err.message) || err);
      self.postMessage({ type: "error", message: loadError });
      waiting.splice(0).forEach(answer);
    });
  }

  self.onmessage = function (e) {
    var msg = e && e.data;
    if (!msg || typeof msg !== "object") return; // malformed: ignore safely
    if (msg.type === "init" && typeof msg.url === "string") {
      if (msg.bodyCut && typeof msg.bodyCut.before === "number" && typeof msg.bodyCut.after === "number") {
        bodyCut = msg.bodyCut;
      }
      if (!loading && !index) load(msg.url);
    } else if (msg.type === "query" && typeof msg.q === "string") {
      if (index || loadError) answer(msg);
      else waiting.push(msg);
    }
  };
})();
