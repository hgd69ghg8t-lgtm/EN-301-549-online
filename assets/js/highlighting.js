// On-arrival search-term highlighting and glossary focus. A link followed
// from search results or header suggestions carries the query as ?h=…;
// this wraps its occurrences in the page body in <mark> so the reader can
// see why they landed here, then removes the parameter from the address
// bar so a copied link stays clean. It also moves keyboard focus to a
// linked glossary definition. Client-side presentation only — the
// generated HTML on disk never changes. Bundled into the main script; it
// does nothing unless a ?h= query or an .az-index is present.
(function () {
  "use strict";

  var api = (window.__site && window.__site.search) || null;

  // ---------- Search-term highlighting on arrival ----------
  var highlightQuery = new URLSearchParams(window.location.search).get("h");
  var contentRoot = document.querySelector(".content");
  if (api && highlightQuery && contentRoot) {
    var highlightToks = api.tokens(highlightQuery).filter(function (t) { return t.length >= 2; });
    var MARK_CAP = 200;
    var marked = 0;
    var walker = document.createTreeWalker(contentRoot, NodeFilter.SHOW_TEXT, {
      acceptNode: function (node) {
        var parent = node.parentNode;
        if (!parent || /^(SCRIPT|STYLE|MARK)$/.test(parent.tagName)) return NodeFilter.FILTER_REJECT;
        return NodeFilter.FILTER_ACCEPT;
      }
    });
    var textNodes = [];
    while (walker.nextNode()) textNodes.push(walker.currentNode);
    textNodes.forEach(function (node) {
      if (marked >= MARK_CAP) return;
      var text = node.nodeValue;
      var lower = text.toLowerCase();
      var pieces = [];
      var cursor = 0;
      while (cursor < text.length && marked < MARK_CAP) {
        var next = -1, tok = null;
        for (var i = 0; i < highlightToks.length; i++) {
          var at = lower.indexOf(highlightToks[i], cursor);
          if (at !== -1 && (next === -1 || at < next)) { next = at; tok = highlightToks[i]; }
        }
        if (next === -1) break;
        pieces.push(document.createTextNode(text.slice(cursor, next)));
        var mark = document.createElement("mark");
        mark.className = "search-highlight";
        mark.textContent = text.slice(next, next + tok.length);
        pieces.push(mark);
        cursor = next + tok.length;
        marked++;
      }
      if (!pieces.length) return;
      pieces.push(document.createTextNode(text.slice(cursor)));
      var frag = document.createDocumentFragment();
      pieces.forEach(function (p) { frag.appendChild(p); });
      node.parentNode.replaceChild(frag, node);
    });
    var cleanUrl = new URL(window.location.href);
    cleanUrl.searchParams.delete("h");
    window.history.replaceState(null, "", cleanUrl);
  }

  // ---------- Glossary term focus-on-navigate ----------
  // A fragment link to a <dt id="..."> already scrolls it into view via
  // normal browser anchor behaviour. This adds keyboard focus on top, so
  // screen reader and keyboard users landing on a definition get it
  // announced/positioned as the current point — both on load with a
  // fragment already in the URL and when a same-page A-Z index or
  // permalink is activated afterwards. tabindex="-1" (set at build time)
  // makes each <dt> focusable-by-script without adding it to Tab order.
  function focusFragmentTarget() {
    var hash = window.location.hash;
    if (!hash || hash.length < 2) return;
    var target;
    try {
      target = document.getElementById(decodeURIComponent(hash.slice(1)));
    } catch (err) {
      target = document.getElementById(hash.slice(1));
    }
    if (target && target.tagName === "DT") {
      target.focus();
    }
  }
  if (document.querySelector(".az-index")) {
    focusFragmentTarget();
    window.addEventListener("hashchange", focusFragmentTarget);
  }
})();
