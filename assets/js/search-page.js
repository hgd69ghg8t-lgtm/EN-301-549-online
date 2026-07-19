// The full search results page (search.html only — the build includes
// this module solely on that page). It loads the full-text index
// (search-index.json, with body text for recall and snippets) and filters
// it in the browser. Reaching this page needs no JavaScript — the header
// form is a plain GET to search.html; only the live filtering here needs
// script, and the page says so when JS is unavailable (.search-nojs).
// Reuses the shared scoring in window.__site.search so results rank
// exactly like the header suggestions.
(function () {
  "use strict";

  var api = (window.__site && window.__site.search) || null;
  var searchInput = document.getElementById("search-input");
  var searchResults = document.getElementById("search-results");
  var searchCount = document.getElementById("search-count");
  if (!api || !searchInput || !searchResults) return;

  var loadFullIndex = api.makeIndexLoader("search-index.json", ["t", "u"]);
  var SEARCH_LIMIT = 50;
  var index = null;

  // Builds "…text <mark>match</mark> text…" safely via DOM nodes.
  function snippetFor(entry, toks) {
    var frag = document.createDocumentFragment();
    var b = entry.b;
    if (!b) return frag;
    var lower = b.toLowerCase();
    var pos = -1;
    for (var i = 0; i < toks.length; i++) {
      pos = lower.indexOf(toks[i]);
      if (pos !== -1) break;
    }
    if (pos === -1) { pos = 0; }
    var start = Math.max(0, pos - 70);
    var end = Math.min(b.length, pos + 130);
    var slice = b.slice(start, end);
    var sliceLower = slice.toLowerCase();
    if (start > 0) frag.appendChild(document.createTextNode("… "));
    var cursor = 0;
    while (cursor < slice.length) {
      var next = -1, nextTok = null;
      for (var j = 0; j < toks.length; j++) {
        var at = sliceLower.indexOf(toks[j], cursor);
        if (at !== -1 && (next === -1 || at < next)) { next = at; nextTok = toks[j]; }
      }
      if (next === -1) {
        frag.appendChild(document.createTextNode(slice.slice(cursor)));
        break;
      }
      frag.appendChild(document.createTextNode(slice.slice(cursor, next)));
      var mark = document.createElement("mark");
      mark.textContent = slice.slice(next, next + nextTok.length);
      frag.appendChild(mark);
      cursor = next + nextTok.length;
    }
    if (end < b.length) frag.appendChild(document.createTextNode(" …"));
    return frag;
  }

  function runSearch(q) {
    q = q.trim();
    searchResults.textContent = "";
    if (!q) { searchCount.textContent = ""; return; }
    var toks = api.tokens(q);
    var hits = api.hits(index, q);
    var shown = hits.slice(0, SEARCH_LIMIT);
    searchCount.textContent = hits.length === 0
      ? "No results for “" + q + "”. Try fewer or different words, or a clause number."
      : (hits.length > SEARCH_LIMIT
          ? hits.length + " results for “" + q + "” — showing the first " + SEARCH_LIMIT + "."
          : hits.length + (hits.length === 1 ? " result" : " results") + " for “" + q + "”.");
    shown.forEach(function (hit) {
      var li = document.createElement("li");
      var a = document.createElement("a");
      a.href = api.withHighlightParam(hit.e.u, q);
      a.textContent = hit.e.t;
      var where = document.createElement("span");
      where.className = "search-result__page";
      where.textContent = hit.e.p;
      var p = document.createElement("p");
      p.className = "search-result__snippet";
      p.appendChild(snippetFor(hit.e, toks));
      li.appendChild(a);
      li.appendChild(where);
      li.appendChild(p);
      searchResults.appendChild(li);
    });
  }

  var initialQ = new URLSearchParams(window.location.search).get("q") || "";
  searchInput.value = initialQ;

  loadFullIndex().then(function (data) {
    index = data;
    if (initialQ) runSearch(initialQ);
    var timer = null;
    searchInput.addEventListener("input", function () {
      window.clearTimeout(timer);
      timer = window.setTimeout(function () {
        runSearch(searchInput.value);
        var url = new URL(window.location.href);
        if (searchInput.value.trim()) url.searchParams.set("q", searchInput.value.trim());
        else url.searchParams.delete("q");
        window.history.replaceState(null, "", url);
      }, 150);
    });
    searchInput.closest("form").addEventListener("submit", function (e) {
      e.preventDefault();
      runSearch(searchInput.value);
    });
  }).catch(function () {
    searchCount.textContent = "Search couldn’t load its index. Reload the page to try again.";
  });
})();
