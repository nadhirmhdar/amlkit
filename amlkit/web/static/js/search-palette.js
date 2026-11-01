(function () {
  "use strict";

  var overlay = null;
  var input = null;
  var list = null;
  var activeIndex = -1;
  var debounceTimer = null;
  var inflight = null;
  var requestSeq = 0;

  // Fixed destinations, filtered locally. Pages only; nothing here is per-org data.
  var ROUTES = [
    { name: "Dashboard", url: "/dashboard" },
    { name: "Screen a name", url: "/screen" },
    { name: "Customers", url: "/customers" },
    { name: "Onboard a customer", url: "/customers/new" },
    { name: "Alerts", url: "/alerts" },
    { name: "Reports", url: "/reports" },
    { name: "Policies", url: "/policies" },
    { name: "Audit trail", url: "/audit" },
    { name: "Notifications", url: "/notifications" },
    { name: "What's new", url: "/changelog" }
  ];

  function routeItems(q) {
    var low = q.toLowerCase();
    return ROUTES.filter(function (r) {
      return !low || r.name.toLowerCase().indexOf(low) !== -1;
    }).map(function (r) {
      return { type: "page", name: r.name, detail: r.url, url: r.url };
    });
  }

  function createOverlay() {
    overlay = document.createElement("div");
    overlay.id = "search-palette-overlay";
    overlay.style.cssText =
      "position:fixed;inset:0;background:rgba(0,0,0,0.4);z-index:9999;" +
      "display:flex;align-items:flex-start;justify-content:center;padding-top:15vh;";

    var box = document.createElement("div");
    box.style.cssText =
      "background:var(--bg,#fff);border-radius:8px;width:min(560px,90vw);" +
      "box-shadow:0 8px 32px rgba(0,0,0,0.2);overflow:hidden;";

    input = document.createElement("input");
    input.type = "text";
    input.placeholder = "Search customers, alerts, reports, pages…";
    input.setAttribute("aria-label", "Search");
    input.style.cssText =
      "width:100%;padding:14px 18px;border:none;outline:none;" +
      "font-size:16px;background:transparent;color:var(--ink,#222);";

    list = document.createElement("div");
    list.style.cssText = "max-height:320px;overflow-y:auto;";

    box.appendChild(input);
    box.appendChild(list);
    overlay.appendChild(box);
    document.body.appendChild(overlay);

    input.addEventListener("input", function () {
      clearTimeout(debounceTimer);
      debounceTimer = setTimeout(doSearch, 200);
    });

    input.addEventListener("keydown", function (e) {
      var items = list.querySelectorAll("[data-url]");
      if (e.key === "ArrowDown") {
        e.preventDefault();
        activeIndex = Math.min(activeIndex + 1, items.length - 1);
        highlightItem(items);
      } else if (e.key === "ArrowUp") {
        e.preventDefault();
        activeIndex = Math.max(activeIndex - 1, 0);
        highlightItem(items);
      } else if (e.key === "Enter") {
        e.preventDefault();
        var target = items[activeIndex >= 0 ? activeIndex : 0];
        if (target) {
          window.location.href = target.getAttribute("data-url");
        }
      }
    });

    overlay.addEventListener("click", function (e) {
      if (e.target === overlay) close();
    });

    input.focus();
    renderItems(routeItems(""), false);
  }

  function highlightItem(items) {
    for (var i = 0; i < items.length; i++) {
      items[i].style.background = i === activeIndex ? "var(--row-hover,#f0f0f0)" : "";
    }
  }

  function showMessage(text) {
    if (!list) return;
    list.innerHTML = "";
    activeIndex = -1;
    var msg = document.createElement("div");
    msg.style.cssText = "padding:12px 18px;color:var(--ink-2,#888);";
    msg.textContent = text;
    list.appendChild(msg);
  }

  function renderItems(items, truncated) {
    if (!list) return;
    list.innerHTML = "";
    activeIndex = -1;
    items.forEach(function (item) {
      var row = document.createElement("div");
      row.setAttribute("data-url", item.url);
      row.setAttribute("role", "option");
      row.style.cssText =
        "padding:10px 18px;cursor:pointer;display:flex;align-items:center;gap:10px;";
      row.innerHTML =
        '<span style="font-size:11px;text-transform:uppercase;color:var(--ink-2,#888);min-width:60px;">' +
        escapeHtml(item.type) + "</span>" +
        '<span style="font-weight:600;">' + escapeHtml(item.name) + "</span>" +
        '<span style="color:var(--ink-2,#888);font-size:13px;">' + escapeHtml(item.detail) + "</span>";
      row.addEventListener("click", function () {
        window.location.href = item.url;
      });
      row.addEventListener("mouseenter", function () {
        if (!list) return;
        var all = list.querySelectorAll("[data-url]");
        for (var j = 0; j < all.length; j++) {
          if (all[j] === row) activeIndex = j;
          all[j].style.background = "";
        }
        row.style.background = "var(--row-hover,#f0f0f0)";
      });
      list.appendChild(row);
    });
    if (truncated) {
      var note = document.createElement("div");
      note.style.cssText = "padding:8px 18px;font-size:12px;color:var(--ink-2,#888);";
      note.textContent = "Results may be incomplete — refine your search";
      list.appendChild(note);
    }
  }

  function doSearch() {
    if (!input || !list) return;
    var q = input.value.trim();
    if (inflight) { inflight.abort(); inflight = null; }
    var seq = ++requestSeq;
    if (!q) {
      renderItems(routeItems(""), false);
      return;
    }
    var ctrl = typeof AbortController !== "undefined" ? new AbortController() : null;
    inflight = ctrl;
    fetch("/search?q=" + encodeURIComponent(q), {
      credentials: "same-origin",
      headers: { Accept: "application/json" },
      signal: ctrl ? ctrl.signal : undefined
    })
      .then(function (r) {
        var ct = r.headers.get("content-type") || "";
        if (r.redirected || !r.ok || ct.indexOf("application/json") === -1) {
          var err = new Error("search-unavailable");
          err.expired = r.redirected || r.status === 401 || r.status === 303;
          throw err;
        }
        return r.json();
      })
      .then(function (data) {
        if (seq !== requestSeq || !list) return; // stale or palette closed
        var items = (data.results || []).concat(routeItems(q));
        if (!items.length) {
          list.innerHTML = "";
          showMessage("No results found");
          return;
        }
        renderItems(items, !!data.truncated);
      })
      .catch(function (err) {
        if (err && err.name === "AbortError") return;
        if (seq !== requestSeq || !list) return;
        showMessage(err && err.expired
          ? "Session expired — please sign in again"
          : "Search unavailable, try again");
      });
  }

  function escapeHtml(str) {
    var div = document.createElement("div");
    div.textContent = str || "";
    return div.innerHTML;
  }

  function close() {
    clearTimeout(debounceTimer);
    requestSeq++;
    if (inflight) { inflight.abort(); inflight = null; }
    if (overlay) {
      overlay.remove();
      overlay = null;
      input = null;
      list = null;
      activeIndex = -1;
    }
  }

  function open() {
    if (overlay) { close(); return; }
    createOverlay();
  }

  document.addEventListener("keydown", function (e) {
    if ((e.ctrlKey || e.metaKey) && e.key === "k") {
      e.preventDefault();
      open();
    }
    if (e.key === "Escape" && overlay) {
      close();
    }
  });
})();
