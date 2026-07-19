// Page tools: Print, Copy link to this page, and the per-heading copy
// link. These controls are in every page's Page tools menu (heading
// links only on numbered clause/annex pages — guarded), so this is
// bundled into the main script. All are progressive enhancement: Print
// and the heading anchors already work without JavaScript.
(function () {
  "use strict";

  var announce = (window.__site && window.__site.announce) || function () {};

  // Clipboard API first; a legacy execCommand fallback for browsers or
  // contexts where it's unavailable or the permission is denied.
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

  // ---------- Print ----------
  var printBtn = document.querySelector("[data-action='print']");
  if (printBtn) {
    printBtn.addEventListener("click", function () { window.print(); });
  }

  // ---------- Copy page link ----------
  // The button's own label never changes (a stable, predictable
  // accessible name); success/failure is reported through the shared
  // polite live region, plus a small aria-hidden visual status glyph so
  // sighted users get more than a colour-only cue.
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

  // ---------- Heading links ----------
  // Each numbered heading's own text is a self-referencing link (its href
  // already works as a normal same-page anchor with no JS). This only
  // adds a copy-to-clipboard enhancement on top — it does not prevent the
  // default navigation, so keyboard/no-JS users still get a working link.
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
