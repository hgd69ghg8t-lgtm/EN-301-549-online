(function () {
"use strict";
document.documentElement.classList.add("js");
var liveRegion = document.getElementById("status-live");
function announce(message) {
if (!liveRegion) return;
liveRegion.textContent = "";
window.requestAnimationFrame(function () {
liveRegion.textContent = message;
});
}
window.__site = { announce: announce };
})();
(function () {
"use strict";
function searchTokens(q) {
return q.toLowerCase().split(/\s+/).filter(Boolean);
}
function scoreSearchEntry(entry, toks, q) {
var t = (entry.t || "").toLowerCase();
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
function withHighlightParam(u, q) {
var hashAt = u.indexOf("#");
var base = hashAt === -1 ? u : u.slice(0, hashAt);
var hash = hashAt === -1 ? "" : u.slice(hashAt);
return base + (base.indexOf("?") === -1 ? "?" : "&") + "h=" + encodeURIComponent(q) + hash;
}
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
(function () {
"use strict";
var announce = (window.__site && window.__site.announce) || function () {};
var PREFS_KEY = "accessibleDocs.readerPrefs.v1";
var BOOKMARKS_KEY = "accessibleDocs.bookmarks.v1";
var RECENT_KEY = "accessibleDocs.recent.v1";
function storageRead(key, fallback) {
try {
var value = JSON.parse(window.localStorage.getItem(key));
return value === null ? fallback : value;
} catch (err) {
return fallback;
}
}
function storageWrite(key, value) {
try {
window.localStorage.setItem(key, JSON.stringify(value));
return true;
} catch (err) {
announce("This browser could not save that change.");
return false;
}
}
function pageRecord() {
var body = document.body;
return {
slug: body.dataset.pageSlug,
title: body.dataset.pageTitle,
href: body.dataset.pageSlug + ".html"
};
}
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
var defaults = { width: "wide", spacing: false, theme: "auto" };
var stored = storageRead(PREFS_KEY, {});
if (typeof stored !== "object" || stored === null) stored = {};
var prefs = {
width: ["wide", "comfortable"].includes(stored.width) ? stored.width : defaults.width,
spacing: typeof stored.spacing === "boolean" ? stored.spacing : defaults.spacing,
theme: ["auto", "light", "dark"].includes(stored.theme) ? stored.theme : defaults.theme
};
function applyPrefs() {
document.documentElement.dataset.readingWidth = prefs.width;
if (prefs.spacing) document.documentElement.dataset.textSpacing = "enhanced";
else delete document.documentElement.dataset.textSpacing;
if (prefs.theme === "auto") delete document.documentElement.dataset.theme;
else document.documentElement.dataset.theme = prefs.theme;
if (window.__syncThemeColour) window.__syncThemeColour(prefs.theme);
document.querySelectorAll('input[name="reading-width"]').forEach(function (input) {
input.checked = input.value === prefs.width;
});
document.querySelectorAll('input[name="colour-theme"]').forEach(function (input) {
input.checked = input.value === prefs.theme;
});
var spacing = document.querySelector("[data-reading-spacing]");
if (spacing) spacing.checked = Boolean(prefs.spacing);
}
applyPrefs();
document.querySelectorAll('input[name="reading-width"]').forEach(function (input) {
input.addEventListener("change", function () {
if (!input.checked) return;
prefs.width = input.value;
applyPrefs();
storageWrite(PREFS_KEY, prefs);
});
});
document.querySelectorAll('input[name="colour-theme"]').forEach(function (input) {
input.addEventListener("change", function () {
if (!input.checked) return;
prefs.theme = input.value;
applyPrefs();
storageWrite(PREFS_KEY, prefs);
});
});
var spacing = document.querySelector("[data-reading-spacing]");
if (spacing) spacing.addEventListener("change", function () {
prefs.spacing = spacing.checked;
applyPrefs();
storageWrite(PREFS_KEY, prefs);
});
var reset = document.querySelector("[data-reader-reset]");
if (reset) reset.addEventListener("click", function () {
prefs = { width: "wide", spacing: false, theme: "auto" };
applyPrefs();
storageWrite(PREFS_KEY, prefs);
announce("Reading options reset.");
});
var record = pageRecord();
var bookmarks = storageRead(BOOKMARKS_KEY, []);
if (!Array.isArray(bookmarks)) bookmarks = [];
var bookmark = document.querySelector("[data-action='bookmark']");
function updateBookmark() {
if (!bookmark) return;
var saved = bookmarks.some(function (item) { return item.slug === record.slug; });
bookmark.setAttribute("aria-pressed", String(saved));
bookmark.querySelector(".bookmark-label").textContent = saved ? "Remove bookmark" : "Bookmark page";
}
if (bookmark) bookmark.addEventListener("click", function () {
var index = bookmarks.findIndex(function (item) { return item.slug === record.slug; });
if (index === -1) {
bookmarks.unshift(record);
bookmarks = bookmarks.slice(0, 50);
announce("Page bookmarked.");
} else {
bookmarks.splice(index, 1);
announce("Bookmark removed.");
}
storageWrite(BOOKMARKS_KEY, bookmarks);
updateBookmark();
renderReaderList("[data-bookmarks-list]", bookmarks, "No bookmarks yet.");
});
updateBookmark();
renderReaderList("[data-bookmarks-list]", bookmarks, "No bookmarks yet.");
var recent = storageRead(RECENT_KEY, []);
if (!Array.isArray(recent)) recent = [];
if (document.body.dataset.pageGroup) {
recent = recent.filter(function (item) { return item.slug !== record.slug; });
recent.unshift(record);
recent = recent.slice(0, 10);
storageWrite(RECENT_KEY, recent);
}
renderReaderList("[data-recent-list]", recent, "No recently viewed pages yet.");
})();
(function () {
"use strict";
var toggle = document.querySelector(".toc-toggle");
var nav = document.querySelector(".site-nav");
function closeNav() {
if (!nav) return;
nav.classList.remove("is-open");
if (toggle) {
toggle.setAttribute("aria-expanded", "false");
toggle.focus();
}
}
if (toggle && nav) {
toggle.addEventListener("click", function () {
var open = nav.classList.toggle("is-open");
toggle.setAttribute("aria-expanded", open ? "true" : "false");
});
}
document.addEventListener("keydown", function (e) {
if (e.key === "Escape" && nav && nav.classList.contains("is-open")) {
closeNav();
}
});
var searchToggle = document.querySelector(".search-toggle");
var searchForm = document.querySelector(".site-search");
if (searchToggle && searchForm) {
var headerSearchInput = searchForm.querySelector("input[type='search']");
searchToggle.addEventListener("click", function () {
var open = searchForm.classList.toggle("is-open");
searchToggle.setAttribute("aria-expanded", open ? "true" : "false");
if (open && headerSearchInput) headerSearchInput.focus();
});
searchForm.addEventListener("keydown", function (e) {
if (e.key === "Escape" && searchForm.classList.contains("is-open")) {
searchForm.classList.remove("is-open");
searchToggle.setAttribute("aria-expanded", "false");
searchToggle.focus();
}
});
}
var pageTools = document.querySelector(".page-tools");
if (pageTools) {
pageTools.addEventListener("keydown", function (e) {
if (e.key === "Escape" && pageTools.open) {
pageTools.open = false;
pageTools.querySelector("summary").focus();
}
});
}
var backToTop = document.querySelector(".back-to-top");
if (backToTop) {
window.addEventListener("scroll", function () {
if (window.scrollY > 400) {
backToTop.classList.add("is-visible");
} else {
backToTop.classList.remove("is-visible");
}
}, { passive: true });
}
var tocLinks = document.querySelectorAll(".site-nav__subsections a[data-subsection]");
if (tocLinks.length) {
var headings = [];
tocLinks.forEach(function (link) {
var id = link.getAttribute("href").slice(1);
var heading = document.getElementById(id);
if (heading) headings.push({ link: link, el: heading });
});
var ACTIVE_LINE = 120;
var ticking = false;
function updateActive() {
ticking = false;
var active = headings[0];
for (var i = 0; i < headings.length; i++) {
if (headings[i].el.getBoundingClientRect().top <= ACTIVE_LINE) {
active = headings[i];
} else {
break;
}
}
tocLinks.forEach(function (link) { link.removeAttribute("aria-current"); });
if (active) active.link.setAttribute("aria-current", "location");
}
function onScroll() {
if (!ticking) {
ticking = true;
window.requestAnimationFrame(updateActive);
}
}
if (headings.length) {
updateActive();
window.addEventListener("scroll", onScroll, { passive: true });
window.addEventListener("resize", onScroll);
}
}
})();
(function () {
"use strict";
var announce = (window.__site && window.__site.announce) || function () {};
function copyText(text) {
if (navigator.clipboard && navigator.clipboard.writeText) {
return navigator.clipboard.writeText(text);
}
return new Promise(function (resolve, reject) {
var input = document.createElement("textarea");
input.value = text;
input.setAttribute("readonly", "");
input.style.position = "fixed";
input.style.top = "-1000px";
input.style.left = "-1000px";
document.body.appendChild(input);
input.select();
input.setSelectionRange(0, text.length);
var ok = false;
try {
ok = document.execCommand("copy");
} catch (err) {
ok = false;
}
document.body.removeChild(input);
if (ok) { resolve(); } else { reject(new Error("execCommand copy failed")); }
});
}
var printBtn = document.querySelector("[data-action='print']");
if (printBtn) {
printBtn.addEventListener("click", function () { window.print(); });
}
var copyBtn = document.querySelector("[data-action='copy-link']");
if (copyBtn) {
var copyStatus = copyBtn.querySelector(".doc-toolbar__btn-status");
copyBtn.addEventListener("click", function () {
copyText(window.location.href).then(function () {
if (copyStatus) copyStatus.textContent = "✓";
announce("Link copied.");
}, function () {
if (copyStatus) copyStatus.textContent = "⚠";
announce("Couldn't copy the link automatically. You can copy it from the address bar.");
});
if (copyStatus) {
window.setTimeout(function () { copyStatus.textContent = ""; }, 3000);
}
});
}
document.querySelectorAll(".heading-link[data-copy-link]").forEach(function (link) {
link.addEventListener("click", function () {
var url = window.location.origin + window.location.pathname + link.getAttribute("href");
copyText(url).then(function () {
announce("Link to this heading copied.");
}, function () {
announce("Couldn't copy the link automatically. The address bar now shows it instead.");
});
});
});
})();
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
if (headerInput.value.trim() !== q) return;
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
}).catch(function () { });
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
e.preventDefault();
closeSuggest();
}
});
headerInput.addEventListener("blur", function () {
window.setTimeout(closeSuggest, 100);
});
})();
(function () {
"use strict";
var api = (window.__site && window.__site.search) || null;
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
