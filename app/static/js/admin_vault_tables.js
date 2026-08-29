(function () {
  "use strict";

  function escapeHtml(s) {
    var d = document.createElement("div");
    d.textContent = s == null ? "" : String(s);
    return d.innerHTML;
  }

  function dispIso(iso) {
    if (!iso) return "—";
    var normalized = String(iso);
    if (!/(Z|[+-]\d{2}:?\d{2})$/i.test(normalized)) {
      normalized += "Z";
    }
    var dt = new Date(normalized);
    if (isNaN(dt.getTime())) return escapeHtml(iso);
    try {
      return escapeHtml(
        dt.toLocaleString("en-US", {
          timeZone: "America/Chicago",
          timeZoneName: "short",
        })
      );
    } catch (e) {
      return escapeHtml(iso);
    }
  }

  function cmpString(a, b, dir) {
    return String(a || "")
      .toLowerCase()
      .localeCompare(String(b || "").toLowerCase(), undefined, {
        sensitivity: "base",
      }) * dir;
  }

  function cmpIso(a, b, dir) {
    var as = a || "";
    var bs = b || "";
    if (!as && !bs) return 0;
    if (!as) return 1;
    if (!bs) return -1;
    if (as < bs) return -1 * dir;
    if (as > bs) return 1 * dir;
    return 0;
  }

  function initAccessRequestsList() {
    var container = document.getElementById("access-requests-list");
    var searchEl = document.getElementById("access-requests-search");
    var sortEl = document.getElementById("access-requests-sort");
    if (!container) return;

    var blocks = Array.prototype.slice.call(
      container.querySelectorAll(".access-request-block[data-request-id]")
    );
    if (!blocks.length) return;

    function apply() {
      var q = (searchEl && searchEl.value || "").trim().toLowerCase();
      var sort = sortEl ? sortEl.value : "created_desc";
      var visible = blocks.filter(function (block) {
        if (!q) return true;
        var hay = block.getAttribute("data-search") || "";
        return hay.indexOf(q) >= 0;
      });
      visible.sort(function (a, b) {
        if (sort === "created_asc") {
          return cmpIso(
            a.getAttribute("data-created"),
            b.getAttribute("data-created"),
            1
          );
        }
        if (sort === "created_desc") {
          return cmpIso(
            a.getAttribute("data-created"),
            b.getAttribute("data-created"),
            -1
          );
        }
        if (sort === "name_asc") {
          return cmpString(
            a.getAttribute("data-contact-name"),
            b.getAttribute("data-contact-name"),
            1
          );
        }
        if (sort === "name_desc") {
          return cmpString(
            a.getAttribute("data-contact-name"),
            b.getAttribute("data-contact-name"),
            -1
          );
        }
        if (sort === "status_asc") {
          return cmpString(
            a.getAttribute("data-status"),
            b.getAttribute("data-status"),
            1
          );
        }
        if (sort === "ruleset_asc") {
          return cmpString(
            a.getAttribute("data-ruleset"),
            b.getAttribute("data-ruleset"),
            1
          );
        }
        return cmpIso(
          a.getAttribute("data-created"),
          b.getAttribute("data-created"),
          -1
        );
      });
      blocks.forEach(function (block) {
        block.hidden = true;
      });
      visible.forEach(function (block) {
        block.hidden = false;
        container.appendChild(block);
      });
      var empty = document.getElementById("access-requests-empty-filter");
      if (empty) {
        empty.hidden = visible.length > 0;
      }
    }

    if (searchEl) searchEl.addEventListener("input", apply);
    if (sortEl) sortEl.addEventListener("change", apply);
    apply();
  }

  function initCharactersTable() {
    var boot = document.getElementById("characters-bootstrap");
    var tbody = document.getElementById("characters-tbody");
    var searchEl = document.getElementById("characters-search");
    var sortEls = document.querySelectorAll(".characters-sortable");
    if (!boot || !tbody) return;

    var allRows = [];
    try {
      allRows = JSON.parse(boot.textContent || "[]");
    } catch (e) {
      allRows = [];
    }

    var sortCol = "gm_username";
    var sortDir = 1;
    var filterText = "";

    function rowMatches(row) {
      if (!filterText) return true;
      var hay = [
        row.gm_username,
        row.gm_email,
        row.campaign_name,
        row.system_type,
        row.character_name,
        row.player_username,
        row.player_email,
      ]
        .join(" ")
        .toLowerCase();
      return hay.indexOf(filterText) >= 0;
    }

    function cmpVal(a, b, type) {
      if (type === "boolean") {
        var av = a ? 1 : 0;
        var bv = b ? 1 : 0;
        return (av - bv) * sortDir;
      }
      if (type === "iso") {
        return cmpIso(a, b, sortDir);
      }
      return cmpString(a, b, sortDir);
    }

    function render() {
      var rows = allRows.filter(rowMatches);
      var th = document.querySelector(
        '.characters-sortable[data-sort="' + sortCol + '"]'
      );
      var type = th ? th.getAttribute("data-sort-type") || "string" : "string";
      rows.sort(function (x, y) {
        return cmpVal(x[sortCol], y[sortCol], type);
      });
      tbody.innerHTML = "";
      if (!allRows.length) {
        tbody.innerHTML =
          '<tr><td colspan="9" class="text-muted">No users with campaigns found yet.</td></tr>';
        return;
      }
      if (!rows.length) {
        tbody.innerHTML =
          '<tr><td colspan="9" class="text-muted">No rows match your search.</td></tr>';
        return;
      }
      rows.forEach(function (row) {
        var tr = document.createElement("tr");
        tr.innerHTML =
          "<td>" +
          escapeHtml(row.gm_username) +
          "</td>" +
          '<td class="font-monospace small">' +
          escapeHtml(row.gm_email) +
          "</td>" +
          "<td>" +
          escapeHtml(row.campaign_name) +
          "</td>" +
          "<td>" +
          escapeHtml(row.system_type) +
          "</td>" +
          "<td>" +
          (row.is_active
            ? '<span class="badge bg-success">Active</span>'
            : '<span class="badge bg-secondary">Archived</span>') +
          "</td>" +
          "<td>" +
          escapeHtml(row.character_name) +
          "</td>" +
          "<td>" +
          escapeHtml(row.player_username) +
          "</td>" +
          '<td class="font-monospace small">' +
          escapeHtml(row.player_email) +
          "</td>" +
          '<td class="small">' +
          dispIso(row.sheet_updated_at) +
          "</td>";
        tbody.appendChild(tr);
      });
    }

    function updateSortHints(activeTh) {
      document
        .querySelectorAll(".characters-sortable .vault-sort-hint")
        .forEach(function (el) {
          el.textContent = "";
        });
      if (activeTh) {
        var hint = activeTh.querySelector(".vault-sort-hint");
        if (hint) hint.textContent = sortDir === 1 ? "▲" : "▼";
      }
    }

    if (searchEl) {
      searchEl.addEventListener("input", function () {
        filterText = (searchEl.value || "").trim().toLowerCase();
        render();
      });
    }

    sortEls.forEach(function (th) {
      th.addEventListener("click", function () {
        var col = th.getAttribute("data-sort");
        if (sortCol === col) {
          sortDir = sortDir === 1 ? -1 : 1;
        } else {
          sortCol = col;
          sortDir = 1;
        }
        updateSortHints(th);
        render();
      });
    });

    var defaultTh = document.querySelector(
      '.characters-sortable[data-sort="gm_username"]'
    );
    updateSortHints(defaultTh);
    render();
  }

  function initSubmissionQueues() {
    document.querySelectorAll("[data-queue-root]").forEach(function (root) {
      var panels = root.querySelectorAll(".vault-queue-panel");
      var tabBtns = root.querySelectorAll("[data-queue-filter]");
      var searchEl = root.querySelector(".vault-queue-search");
      var sortEl = root.querySelector(".vault-queue-sort");
      var activeFilter = "pending";

      function statusRank(status) {
        if (status === "pending") return 0;
        if (status === "reviewed") return 1;
        if (status === "closed") return 2;
        return 3;
      }

      function applyPanel(panel) {
        var list = panel.querySelector(".vault-queue-list");
        if (!list) return;
        var blocks = Array.prototype.slice.call(
          list.querySelectorAll(".submission-triage-block")
        );
        var q = (searchEl && searchEl.value || "").trim().toLowerCase();
        var sort = sortEl ? sortEl.value : "created_desc";
        var visible = blocks.filter(function (block) {
          if (!q) return true;
          var hay = block.getAttribute("data-search") || "";
          return hay.indexOf(q) >= 0;
        });
        visible.sort(function (a, b) {
          if (sort === "created_asc") {
            return cmpIso(
              a.getAttribute("data-created"),
              b.getAttribute("data-created"),
              1
            );
          }
          if (sort === "created_desc") {
            return cmpIso(
              a.getAttribute("data-created"),
              b.getAttribute("data-created"),
              -1
            );
          }
          if (sort === "username_asc") {
            return cmpString(
              a.getAttribute("data-username"),
              b.getAttribute("data-username"),
              1
            );
          }
          if (sort === "username_desc") {
            return cmpString(
              a.getAttribute("data-username"),
              b.getAttribute("data-username"),
              -1
            );
          }
          if (sort === "status_asc") {
            var diff =
              statusRank(a.getAttribute("data-status")) -
              statusRank(b.getAttribute("data-status"));
            return diff !== 0 ? diff : cmpIso(
              a.getAttribute("data-created"),
              b.getAttribute("data-created"),
              -1
            );
          }
          return cmpIso(
            a.getAttribute("data-created"),
            b.getAttribute("data-created"),
            -1
          );
        });
        blocks.forEach(function (block) {
          block.hidden = true;
        });
        visible.forEach(function (block) {
          block.hidden = false;
          list.appendChild(block);
        });
        var emptyMsg = panel.querySelector(".vault-queue-empty-msg");
        if (emptyMsg) {
          emptyMsg.hidden = visible.length > 0;
        }
      }

      function applyAllPanels() {
        panels.forEach(applyPanel);
      }

      tabBtns.forEach(function (btn) {
        btn.addEventListener("click", function () {
          activeFilter = btn.getAttribute("data-queue-filter") || "all";
          tabBtns.forEach(function (b) {
            b.classList.toggle("active", b === btn);
            b.setAttribute("aria-selected", b === btn ? "true" : "false");
          });
          panels.forEach(function (panel) {
            var match =
              panel.getAttribute("data-queue-panel") === activeFilter;
            panel.hidden = !match;
          });
          applyAllPanels();
        });
      });

      if (searchEl) searchEl.addEventListener("input", applyAllPanels);
      if (sortEl) sortEl.addEventListener("change", applyAllPanels);
      applyAllPanels();
    });
  }

  function renderBreakdownTable(tbody, rows) {
    if (!tbody) return;
    if (!rows || !rows.length) {
      tbody.innerHTML =
        '<tr><td colspan="2" class="text-muted">No data yet.</td></tr>';
      return;
    }
    tbody.innerHTML = rows
      .map(function (row) {
        return (
          "<tr><td>" +
          escapeHtml(row.label) +
          "</td><td>" +
          escapeHtml(row.count) +
          "</td></tr>"
        );
      })
      .join("");
  }

  function initClientAnalyticsTab() {
    var boot = document.getElementById("client-analytics-bootstrap");
    if (!boot) return;

    var filterBtn = document.getElementById("client-analytics-filter-btn");
    var sinceEl = document.getElementById("client-analytics-since");
    var untilEl = document.getElementById("client-analytics-until");
    var demoRunsEl = document.getElementById("client-analytics-demo-runs");
    var subCountEl = document.getElementById("client-analytics-submissions");
    var apiUrl = boot.getAttribute("data-api-url") || "";

    function renderPayload(payload) {
      if (!payload) payload = {};
      if (demoRunsEl) {
        demoRunsEl.textContent = String(payload.demo_runs || 0);
      }
      if (subCountEl) {
        subCountEl.textContent = String(payload.submission_count || 0);
      }
      var demo = payload.demo || {};
      var subs = payload.submissions || {};
      renderBreakdownTable(
        document.getElementById("client-demo-browsers-tbody"),
        demo.browsers
      );
      renderBreakdownTable(
        document.getElementById("client-demo-os-tbody"),
        demo.operating_systems
      );
      renderBreakdownTable(
        document.getElementById("client-demo-devices-tbody"),
        demo.devices
      );
      renderBreakdownTable(
        document.getElementById("client-sub-browsers-tbody"),
        subs.browsers
      );
      renderBreakdownTable(
        document.getElementById("client-sub-os-tbody"),
        subs.operating_systems
      );
      renderBreakdownTable(
        document.getElementById("client-sub-devices-tbody"),
        subs.devices
      );
    }

    function querySuffix() {
      var params = [];
      var since = sinceEl && sinceEl.value ? sinceEl.value.trim() : "";
      var until = untilEl && untilEl.value ? untilEl.value.trim() : "";
      if (since) params.push("since=" + encodeURIComponent(since));
      if (until) params.push("until=" + encodeURIComponent(until));
      return params.length ? "?" + params.join("&") : "";
    }

    function applyFilter() {
      if (!apiUrl) return;
      fetch(apiUrl + querySuffix(), {
        method: "GET",
        headers: { Accept: "application/json" },
        credentials: "same-origin",
      })
        .then(function (resp) {
          if (!resp.ok) throw new Error("filter_failed");
          return resp.json();
        })
        .then(renderPayload)
        .catch(function () {
          alert("Could not refresh Client analytics.");
        });
    }

    try {
      renderPayload(JSON.parse(boot.textContent || "{}"));
    } catch (e) {
      renderPayload({});
    }
    if (filterBtn) filterBtn.addEventListener("click", applyFilter);
  }

  function initDemoClientBreakdown() {
    var boot = document.getElementById("demo-analytics-bootstrap");
    if (!boot) return;
    try {
      var payload = JSON.parse(boot.textContent || "{}");
      var breakdown = payload.client_breakdown || {};
      renderBreakdownTable(
        document.getElementById("demo-client-browsers-tbody"),
        breakdown.browsers
      );
      renderBreakdownTable(
        document.getElementById("demo-client-os-tbody"),
        breakdown.operating_systems
      );
      renderBreakdownTable(
        document.getElementById("demo-client-devices-tbody"),
        breakdown.devices
      );
    } catch (e) {
      /* ignore */
    }
  }

  document.addEventListener("DOMContentLoaded", function () {
    initAccessRequestsList();
    initCharactersTable();
    initSubmissionQueues();
    initClientAnalyticsTab();
    initDemoClientBreakdown();

    var params = new URLSearchParams(window.location.search);
    var tab = params.get("tab");
    if (tab) {
      var paneId = "vault-" + tab.replace(/_/g, "-") + "-pane";
      if (tab === "bug_reports") paneId = "vault-bug-reports-pane";
      if (tab === "feedback") paneId = "vault-feedback-pane";
      if (tab === "suggestions") paneId = "vault-suggestions-pane";
      if (tab === "demo-analytics") paneId = "demo-analytics-pane";
      if (tab === "client-analytics") paneId = "client-analytics-pane";
      if (tab === "gm-simulation") paneId = "gm-simulation-pane";
      if (tab === "access-requests") paneId = "vault-access-requests-pane";
      if (tab === "characters") paneId = "vault-characters-pane";
      var trigger = document.querySelector('[data-bs-target="#' + paneId + '"]');
      if (trigger && window.bootstrap && window.bootstrap.Tab) {
        window.bootstrap.Tab.getOrCreateInstance(trigger).show();
      }
    }
  });

  window.adminVaultRenderDemoClientBreakdown = function (payload) {
    var breakdown = (payload && payload.client_breakdown) || {};
    renderBreakdownTable(
      document.getElementById("demo-client-browsers-tbody"),
      breakdown.browsers
    );
    renderBreakdownTable(
      document.getElementById("demo-client-os-tbody"),
      breakdown.operating_systems
    );
    renderBreakdownTable(
      document.getElementById("demo-client-devices-tbody"),
      breakdown.devices
    );
  };
})();
