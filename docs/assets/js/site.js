(function () {
  "use strict";

  // ---------- Mobile contents toggle ----------
  var toggle = document.querySelector(".toc-toggle");
  var nav = document.querySelector(".site-nav");
  var closeBtn = document.querySelector(".site-nav__close");

  function openNav() {
    if (!nav) return;
    nav.classList.add("is-open");
    if (toggle) toggle.setAttribute("aria-expanded", "true");
    if (closeBtn) closeBtn.focus();
  }
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
      var expanded = toggle.getAttribute("aria-expanded") === "true";
      if (expanded) { closeNav(); } else { openNav(); }
    });
  }
  if (closeBtn) {
    closeBtn.addEventListener("click", closeNav);
  }
  document.addEventListener("keydown", function (e) {
    if (e.key === "Escape" && nav && nav.classList.contains("is-open")) {
      closeNav();
    }
  });

  // ---------- Toolbar: print / copy link ----------
  var printBtn = document.querySelector("[data-action='print']");
  if (printBtn) {
    printBtn.addEventListener("click", function () { window.print(); });
  }
  var copyBtn = document.querySelector("[data-action='copy-link']");
  if (copyBtn) {
    var copyLabel = copyBtn.querySelector(".doc-toolbar__btn-label");
    copyBtn.addEventListener("click", function () {
      navigator.clipboard.writeText(window.location.href).then(function () {
        if (copyLabel) {
          var original = copyLabel.textContent;
          copyLabel.textContent = "Link copied!";
          setTimeout(function () { copyLabel.textContent = original; }, 2000);
        }
      });
    });
  }

  // ---------- Back to top ----------
  var backToTop = document.querySelector(".back-to-top");
  if (backToTop) {
    window.addEventListener("scroll", function () {
      if (window.scrollY > 400) {
        backToTop.classList.add("is-visible");
      } else {
        backToTop.classList.remove("is-visible");
      }
    }, { passive: true });
    backToTop.addEventListener("click", function () {
      window.scrollTo({ top: 0, behavior: "smooth" });
    });
  }

  // ---------- In-page contents: active section highlight ----------
  var tocLinks = document.querySelectorAll(".page-toc a[href^='#']");
  if (tocLinks.length && "IntersectionObserver" in window) {
    var linkById = {};
    var headings = [];
    tocLinks.forEach(function (link) {
      var id = link.getAttribute("href").slice(1);
      var heading = document.getElementById(id);
      if (heading) {
        headings.push(heading);
        linkById[id] = link;
      }
    });

    var visible = new Map();
    var observer = new IntersectionObserver(function (entries) {
      entries.forEach(function (entry) {
        if (entry.isIntersecting) {
          visible.set(entry.target.id, entry.intersectionRatio);
        } else {
          visible.delete(entry.target.id);
        }
      });
      if (visible.size > 0) {
        var best = null;
        visible.forEach(function (ratio, id) {
          if (!best || ratio > visible.get(best)) best = id;
        });
        tocLinks.forEach(function (link) { link.removeAttribute("aria-current"); });
        if (linkById[best]) linkById[best].setAttribute("aria-current", "location");
      }
    }, { rootMargin: "-10% 0px -70% 0px", threshold: [0, 0.5, 1] });

    headings.forEach(function (h) { observer.observe(h); });
  }
})();
