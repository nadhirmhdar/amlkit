(function () {
  "use strict";

  var activePanel = null;
  var activeRow = null;

  // Closing returns focus to the row that opened the panel, so a keyboard user
  // is not dropped at the top of the page when the panel disappears.
  function closePanel(restoreFocus) {
    var row = activeRow;
    if (activePanel) {
      activePanel.remove();
      activePanel = null;
    }
    if (activeRow) {
      activeRow.classList.remove("alert-row-active");
      activeRow.setAttribute("aria-expanded", "false");
      activeRow.removeAttribute("aria-controls");
      activeRow = null;
    }
    if (restoreFocus === true && row && document.body.contains(row)) row.focus();
  }

  function openPanel(row, alertId) {
    if (activeRow === row) {
      closePanel(true);
      return;
    }
    closePanel();

    activeRow = row;
    row.classList.add("alert-row-active");
    row.setAttribute("aria-expanded", "true");

    var container = document.createElement("div");
    container.className = "alert-panel-container";
    container.id = "alert-panel-" + alertId;
    container.setAttribute("role", "region");
    container.setAttribute("aria-label", "Alert details");
    container.setAttribute("aria-live", "polite");
    container.setAttribute("tabindex", "-1");
    row.setAttribute("aria-controls", container.id);
    container.textContent = "Loading…";
    row.parentNode.insertBefore(container, row.nextSibling);
    activePanel = container;

    fetch("/alerts/" + alertId + "/panel")
      .then(function (r) {
        if (!r.ok || r.redirected) throw new Error(r.status);
        return r.text();
      })
      .then(function (html) {
        if (activePanel !== container) return;
        container.innerHTML = html;
        var closeBtn = container.querySelector(".alert-panel-close");
        if (closeBtn) {
          closeBtn.addEventListener("click", function () { closePanel(true); });
        }
        // Move focus into the panel so keyboard and screen-reader users land
        // on the content they just asked for.
        container.focus();
      })
      .catch(function () {
        if (activePanel === container) {
          container.setAttribute("role", "alert");
          container.textContent = "Could not load alert details. Close this row and try again.";
        }
      });
  }

  document.addEventListener("click", function (e) {
    if (e.defaultPrevented || e.button !== 0 ||
        e.ctrlKey || e.metaKey || e.shiftKey || e.altKey) return;
    var row = e.target.closest(".list-row[data-alert-id]");
    if (row) {
      e.preventDefault();
      openPanel(row, row.getAttribute("data-alert-id"));
    }
  });

  // Escape closes an open panel, but never while the user is typing in a field
  // inside it (that would throw away what they had entered).
  document.addEventListener("keydown", function (e) {
    if (e.key !== "Escape" || !activePanel) return;
    var t = e.target;
    if (t && t.closest && t.closest("input, textarea, select")) return;
    closePanel(true);
  });
})();
