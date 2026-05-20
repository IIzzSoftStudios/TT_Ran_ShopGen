(function () {
  "use strict";

  var popover;
  var messageNode;
  var confirmButton;
  var cancelButton;
  var activeRequest = null;

  function ensureStyles() {
    if (document.getElementById("confirm-delete-popover-styles")) {
      return;
    }

    var style = document.createElement("style");
    style.id = "confirm-delete-popover-styles";
    style.textContent = [
      ".confirm-delete-popover {",
      "  display: none;",
      "  position: fixed;",
      "  z-index: 10000;",
      "  width: min(340px, calc(100vw - 24px));",
      "  padding: 16px;",
      "  color: #f8fafc;",
      "  background: #111827;",
      "  border: 1px solid rgba(148, 163, 184, 0.45);",
      "  border-radius: 12px;",
      "  box-shadow: 0 18px 45px rgba(0, 0, 0, 0.45);",
      "}",
      ".confirm-delete-popover.is-open { display: block; }",
      ".confirm-delete-popover__message {",
      "  margin: 0 0 14px;",
      "  line-height: 1.45;",
      "  font-size: 0.95rem;",
      "}",
      ".confirm-delete-popover__actions {",
      "  display: flex;",
      "  justify-content: flex-end;",
      "  gap: 10px;",
      "}",
      ".confirm-delete-popover__button {",
      "  border: 0;",
      "  border-radius: 999px;",
      "  cursor: pointer;",
      "  font-weight: 700;",
      "  padding: 8px 14px;",
      "}",
      ".confirm-delete-popover__cancel {",
      "  color: #e5e7eb;",
      "  background: #374151;",
      "}",
      ".confirm-delete-popover__confirm {",
      "  color: #fff;",
      "  background: #dc3545;",
      "}",
      ".confirm-delete-popover__button:hover,",
      ".confirm-delete-popover__button:focus-visible {",
      "  filter: brightness(1.08);",
      "  outline: 2px solid rgba(147, 197, 253, 0.9);",
      "  outline-offset: 2px;",
      "}",
    ].join("\n");
    document.head.appendChild(style);
  }

  function placePopover(trigger) {
    var margin = 12;
    var gap = 8;
    var rect = trigger.getBoundingClientRect();
    var popoverRect = popover.getBoundingClientRect();
    var left = Math.min(
      Math.max(margin, rect.left),
      window.innerWidth - popoverRect.width - margin
    );
    var top = rect.bottom + gap;

    if (top + popoverRect.height + margin > window.innerHeight) {
      top = rect.top - popoverRect.height - gap;
    }
    if (top < margin) {
      top = margin;
    }

    popover.style.left = left + "px";
    popover.style.top = top + "px";
  }

  function hidePopover() {
    if (!popover) {
      return;
    }

    popover.classList.remove("is-open");
    activeRequest = null;
  }

  function ensurePopover() {
    if (popover) {
      return popover;
    }

    ensureStyles();

    popover = document.createElement("div");
    popover.id = "confirm-delete-popover";
    popover.className = "confirm-delete-popover";
    popover.setAttribute("role", "dialog");
    popover.setAttribute("aria-labelledby", "confirm-delete-popover-message");

    messageNode = document.createElement("p");
    messageNode.id = "confirm-delete-popover-message";
    messageNode.className = "confirm-delete-popover__message";

    var actions = document.createElement("div");
    actions.className = "confirm-delete-popover__actions";

    cancelButton = document.createElement("button");
    cancelButton.type = "button";
    cancelButton.className = "confirm-delete-popover__button confirm-delete-popover__cancel";
    cancelButton.textContent = "Cancel";

    confirmButton = document.createElement("button");
    confirmButton.type = "button";
    confirmButton.className = "confirm-delete-popover__button confirm-delete-popover__confirm";
    confirmButton.textContent = "Delete";

    actions.appendChild(cancelButton);
    actions.appendChild(confirmButton);
    popover.appendChild(messageNode);
    popover.appendChild(actions);
    document.body.appendChild(popover);

    cancelButton.addEventListener("click", hidePopover);
    confirmButton.addEventListener("click", function () {
      var form = activeRequest && activeRequest.form;
      hidePopover();
      if (form) {
        HTMLFormElement.prototype.submit.call(form);
      }
    });

    document.addEventListener("keydown", function (e) {
      if (e.key === "Escape") {
        hidePopover();
      }
    });

    document.addEventListener("mousedown", function (e) {
      if (!activeRequest || popover.contains(e.target) || activeRequest.trigger.contains(e.target)) {
        return;
      }
      hidePopover();
    });

    window.addEventListener("resize", function () {
      if (activeRequest) {
        placePopover(activeRequest.trigger);
      }
    });

    return popover;
  }

  function showPopover(form, trigger, msg) {
    ensurePopover();

    activeRequest = {
      form: form,
      trigger: trigger,
    };
    messageNode.textContent = msg;

    popover.classList.add("is-open");

    placePopover(trigger);
    cancelButton.focus();
  }

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
          showPopover(form, btn, msg);
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
