(function () {
  "use strict";

  var activePanel = null;
  var activeRow = null;

  function closePanel() {
    if (activePanel) {
      activePanel.remove();
      activePanel = null;
    }
    if (activeRow) {
      activeRow.classList.remove("alert-row-active");
      activeRow = null;
    }
  }

  function openPanel(row, alertId) {
    if (activeRow === row) {
      closePanel();
      return;
    }
    closePanel();

    activeRow = row;
    row.classList.add("alert-row-active");

    var container = document.createElement("div");
    container.className = "alert-panel-container";
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
          closeBtn.addEventListener("click", closePanel);
        }
      })
      .catch(function () {
        if (activePanel === container) {
          container.textContent = "Could not load alert details.";
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

  document.addEventListener("keydown", function (e) {
    if (e.key === "Escape") {
      closePanel();
    }
  });
})();
