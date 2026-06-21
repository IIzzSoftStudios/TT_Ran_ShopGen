(function () {
  "use strict";

  function getCsrfToken() {
    var meta = document.querySelector('meta[name="csrf-token"]');
    return meta ? meta.getAttribute("content") : "";
  }

  document.addEventListener("DOMContentLoaded", function () {
    document.querySelectorAll(".action-triage-btn").forEach(function (btn) {
      btn.addEventListener("click", function (e) {
        e.preventDefault();
        var block = btn.closest(".submission-triage-block");
        if (!block) return;
        var id = block.getAttribute("data-submission-id");
        var action = btn.getAttribute("data-action");
        var headers = { "Content-Type": "application/json" };
        var csrf = getCsrfToken();
        if (csrf) headers["X-CSRFToken"] = csrf;
        fetch("/admin/vault/submissions/" + id + "/" + action, {
          method: "POST",
          headers: headers,
          credentials: "same-origin",
        })
          .then(function (res) {
            return res.json().then(function (data) {
              return { ok: res.ok, data: data };
            });
          })
          .then(function (result) {
            if (!result.ok || !result.data.success) {
              alert((result.data && result.data.error) || "Action failed.");
              return;
            }
            var dot = block.querySelector(".submission-status-dot");
            if (dot) {
              if (result.data.new_status === "reviewed") {
                dot.style.background = "#0d6efd";
                dot.setAttribute("data-status", "reviewed");
              } else if (result.data.new_status === "closed") {
                dot.style.background = "#6c757d";
                dot.setAttribute("data-status", "closed");
              }
            }
            if (action === "review") {
              btn.remove();
            } else if (action === "close") {
              var actions = block.querySelector(".submission-triage-actions");
              if (actions) {
                actions.innerHTML = '<p class="text-muted small mb-0">Archived</p>';
              }
            }
          })
          .catch(function (err) {
            console.error("triage action failed", err);
          });
      });
    });

    var params = new URLSearchParams(window.location.search);
    var tab = params.get("tab");
    if (tab) {
      var paneId = "vault-" + tab.replace(/_/g, "-") + "-pane";
      if (tab === "bug_reports") paneId = "vault-bug-reports-pane";
      if (tab === "feedback") paneId = "vault-feedback-pane";
      if (tab === "suggestions") paneId = "vault-suggestions-pane";
      var trigger = document.querySelector('[data-bs-target="#' + paneId + '"]');
      if (trigger && window.bootstrap && window.bootstrap.Tab) {
        window.bootstrap.Tab.getOrCreateInstance(trigger).show();
      }
    }
  });
})();
