/*
  reader-library.js — the saved-pages interface inside Reading options.

  Loaded by core.js the first time the Reading options disclosure opens
  (the lists aren't visible before then, so rendering them during
  initial page load would be pure waste). core.js keeps the parts that
  must work regardless: the bookmark button itself, recording the visit
  for "Recently viewed", and every reading preference.

  If this module never arrives, the panel still works — the lists just
  keep their static "No bookmarks yet." placeholder text.
*/
(function () {
  "use strict";

  var shared = window.AccessibleDocs || {};
  var storageRead = shared.storageRead || function (key, fallback) {
    try {
      var value = JSON.parse(window.localStorage.getItem(key));
      return value === null ? fallback : value;
    } catch (err) {
      return fallback;
    }
  };

  var BOOKMARKS_KEY = "accessibleDocs.bookmarks.v1";
  var RECENT_KEY = "accessibleDocs.recent.v1";

  function renderReaderList(selector, items, emptyText) {
    var list = document.querySelector(selector);
    if (!list) return;
    list.textContent = "";
    if (!items.length) {
      var empty = document.createElement("li");
      empty.textContent = emptyText;
      list.appendChild(empty);
      return;
    }
    items.forEach(function (item) {
      var li = document.createElement("li");
      var a = document.createElement("a");
      a.href = item.href;
      a.textContent = item.title;
      li.appendChild(a);
      list.appendChild(li);
    });
  }

  function renderAll() {
    var bookmarks = storageRead(BOOKMARKS_KEY, []);
    if (!Array.isArray(bookmarks)) bookmarks = [];
    renderReaderList("[data-bookmarks-list]", bookmarks, "No bookmarks yet.");
    var recent = storageRead(RECENT_KEY, []);
    if (!Array.isArray(recent)) recent = [];
    renderReaderList("[data-recent-list]", recent, "No recently viewed pages yet.");
  }

  renderAll();
  // Re-render whenever core.js changes the stored bookmarks (the page's
  // own bookmark button) while the panel is open.
  document.addEventListener("accessibledocs:library-change", renderAll);
})();
