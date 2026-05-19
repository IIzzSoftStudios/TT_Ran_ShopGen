(function () {
  "use strict";

  function wireConfirmDeleteForms(root) {
    var scope = root || document;
    scope.querySelectorAll("form[data-confirm-delete]").forEach(function (form) {
      if (form.dataset.confirmDeleteWired === "1") {
        return;
      }
      form.dataset.confirmDeleteWired = "1";

      var msg = form.getAttribute("data-confirm-delete");
      if (!msg) {
        return;
      }

      form.querySelectorAll('button[type="submit"], input[type="submit"]').forEach(function (btn) {
        btn.type = "button";
        btn.addEventListener("click", function (e) {
          e.preventDefault();
          if (!window.confirm(msg)) {
            return;
          }
          form.submit();
        });
      });
    });
  }

  function init() {
    wireConfirmDeleteForms(document);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
