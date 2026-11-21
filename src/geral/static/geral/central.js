// Central (docs/features/central.md): round arrows, and tabs, séries, filters and pages that swap
// the content in place, keeping the scroll, instead of loading a new page at the top. Without
// JavaScript (or on any error) the links work as plain links.
(function () {
  function initRounds(root) {
    root.querySelectorAll("[data-rounds]").forEach(function (box) {
      var rounds = Array.prototype.slice.call(box.querySelectorAll(".round"));
      var label = box.querySelector(".round-label");
      var prev = box.querySelector('[data-step="-1"]'), next = box.querySelector('[data-step="1"]');
      var at = rounds.findIndex(function (r) { return !r.hidden; });
      if (!rounds.length || at < 0) return;
      function show(i) {
        rounds[at].hidden = true; at = i; rounds[at].hidden = false;
        label.textContent = "Rodada " + rounds[at].dataset.round;
        prev.disabled = at === 0; next.disabled = at === rounds.length - 1;
      }
      [prev, next].forEach(function (b) {
        b.addEventListener("click", function () { show(at + Number(b.dataset.step)); });
      });
      show(at);
    });
  }

  function swap(url, push, toList) {
    return fetch(url, { credentials: "same-origin" })
      .then(function (r) { if (!r.ok) throw new Error(r.status); return r.text(); })
      .then(function (html) {
        var doc = new DOMParser().parseFromString(html, "text/html");
        var next = doc.querySelector("[data-central]"), cur = document.querySelector("[data-central]");
        if (!next || !cur) throw new Error("no content");
        var y = window.scrollY;
        cur.replaceWith(next);
        document.title = doc.title;
        if (push) history.pushState({ central: true }, "", url);
        window.scrollTo(0, y);
        var list = toList && next.querySelector(".news-filter");
        if (list && list.getBoundingClientRect().top < 0) list.scrollIntoView();
        initRounds(next);
      })
      .catch(function () { window.location.href = url; });
  }

  document.addEventListener("click", function (e) {
    var a = e.target.closest && e.target.closest("a[data-swap]");
    if (!a || e.defaultPrevented || e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
    e.preventDefault();
    swap(a.href, true, a.dataset.swap === "list");
  });
  window.addEventListener("popstate", function (e) {
    if (e.state && e.state.central) swap(window.location.href, false, false);
  });
  history.replaceState({ central: true }, "");
  initRounds(document);
})();
