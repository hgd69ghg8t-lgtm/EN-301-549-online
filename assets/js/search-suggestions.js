// Header search suggestions: progressive enhancement over the header's
// plain GET form. Typing shows the top matching clause/heading/term
// titles as an ARIA listbox so a reader can jump straight to a clause
// without the results page. Loads only the small suggestion index
// (search-suggestions.json — titles/URLs, no body text). Without
// JavaScript, or if the suggestion index fails to load, the form still
// submits to search.html exactly as before. Bundled into the main script
// (the header form is on every page); it deliberately does nothing on
// search.html, where the results page owns the input.
(function () {
  "use strict";

  var api = (window.__site && window.__site.search) || null;
  var announce = (window.__site && window.__site.announce) || function () {};

  var headerForm = document.querySelector(".site-search");
  var headerInput = headerForm && headerForm.querySelector("input[type='search']");
  if (!api || !headerForm || !headerInput || document.getElementById("search-input")) return;

  var loadSuggestIndex = api.makeIndexLoader("search-suggestions.json", ["t", "u"]);

  var SUGGEST_LIMIT = 7;
  var suggestList = document.createElement("ul");
  suggestList.id = "search-suggestions";
  suggestList.className = "search-suggest";
  suggestList.setAttribute("role", "listbox");
  suggestList.setAttribute("aria-label", "Search suggestions");
  suggestList.hidden = true;
  headerForm.appendChild(suggestList);
  headerInput.setAttribute("role", "combobox");
  headerInput.setAttribute("aria-expanded", "false");
  headerInput.setAttribute("aria-controls", "search-suggestions");
  headerInput.setAttribute("aria-autocomplete", "list");
  var activeIndex = -1;

  function closeSuggest() {
    suggestList.hidden = true;
    suggestList.textContent = "";
    headerInput.setAttribute("aria-expanded", "false");
    headerInput.removeAttribute("aria-activedescendant");
    activeIndex = -1;
  }

  function setActive(next) {
    var options = suggestList.children;
    if (!options.length) return;
    if (activeIndex >= 0) options[activeIndex].removeAttribute("aria-selected");
    activeIndex = (next + options.length) % options.length;
    var opt = options[activeIndex];
    opt.setAttribute("aria-selected", "true");
    headerInput.setAttribute("aria-activedescendant", opt.id);
  }

  function renderSuggestions(q) {
    loadSuggestIndex().then(function (data) {
      if (headerInput.value.trim() !== q) return; // stale response
      var shown = api.hits(data, q).slice(0, SUGGEST_LIMIT);
      closeSuggest();
      if (!shown.length) return;
      shown.forEach(function (hit, i) {
        var li = document.createElement("li");
        li.id = "search-suggestion-" + i;
        li.setAttribute("role", "option");
        li.dataset.href = api.withHighlightParam(hit.e.u, q);
        var title = document.createElement("span");
        title.className = "search-suggest__title";
        title.textContent = hit.e.t;
        var where = document.createElement("span");
        where.className = "search-suggest__page";
        where.textContent = hit.e.p;
        li.appendChild(title);
        li.appendChild(where);
        // mousedown, not click: click fires after the input's blur has
        // already closed and emptied the list.
        li.addEventListener("mousedown", function (e) {
          e.preventDefault();
          window.location.href = li.dataset.href;
        });
        suggestList.appendChild(li);
      });
      suggestList.hidden = false;
      headerInput.setAttribute("aria-expanded", "true");
      announce(shown.length + (shown.length === 1 ? " suggestion" : " suggestions") +
               " available. Use up and down arrows to review them.");
    }).catch(function () { /* suggestions are optional; the form still submits */ });
  }

  var suggestTimer = null;
  headerInput.addEventListener("input", function () {
    window.clearTimeout(suggestTimer);
    var q = headerInput.value.trim();
    if (q.length < 2) { closeSuggest(); return; }
    suggestTimer = window.setTimeout(function () { renderSuggestions(q); }, 150);
  });
  headerInput.addEventListener("keydown", function (e) {
    if (suggestList.hidden) return;
    if (e.key === "ArrowDown") { e.preventDefault(); setActive(activeIndex + 1); }
    else if (e.key === "ArrowUp") { e.preventDefault(); setActive(activeIndex - 1); }
    else if (e.key === "Enter" && activeIndex >= 0) {
      e.preventDefault();
      window.location.href = suggestList.children[activeIndex].dataset.href;
    } else if (e.key === "Escape") {
      // Close the list but keep the typed text (the browser's default for
      // Escape in a search input is to clear it) — a second Escape, with
      // the list already closed, still clears as normal.
      e.preventDefault();
      closeSuggest();
    }
  });
  headerInput.addEventListener("blur", function () {
    window.setTimeout(closeSuggest, 100);
  });
})();
