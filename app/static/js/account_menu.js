(function () {
  "use strict";

  function getConfig() {
    var el = document.getElementById("tt-account-menu-config");
    if (!el) return {};
    try {
      return JSON.parse(el.textContent || "{}");
    } catch (e) {
      console.warn("account menu config parse failed", e);
      return {};
    }
  }

  function getCsrfToken() {
    var meta = document.querySelector('meta[name="csrf-token"]');
    return meta ? meta.getAttribute("content") : "";
  }

  document.addEventListener("DOMContentLoaded", function () {
    var wrapper = document.getElementById("accountMenuWrapper");
    if (!wrapper) return;

    document.documentElement.classList.add("has-account-menu");

    var config = getConfig();
    var avatarBtn = document.getElementById("accountAvatarBtn");
    var popoverPanel = document.getElementById("accountPopoverPanel");
    var uploadTrigger = document.getElementById("avatarUploadTriggerArea");
    var fileInput = document.getElementById("silentAvatarFileEl");

    function resetToMain() {
      wrapper.querySelectorAll(".popover-frame").forEach(function (frame) {
        frame.classList.add("account-menu-hidden");
      });
      var main = wrapper.querySelector('.popover-frame[data-frame-id="main"]');
      if (main) main.classList.remove("account-menu-hidden");
    }

    function populateCategoryDropdown(kind) {
      var frame = wrapper.querySelector('.popover-frame[data-frame-id="' + kind + '"]');
      if (!frame) return;
      var select = frame.querySelector('select[name="category"]');
      if (!select || select.options.length > 0) return;
      var categories = (config.submission_categories && config.submission_categories[kind]) || [];
      categories.forEach(function (cat) {
        var opt = document.createElement("option");
        opt.value = cat;
        opt.textContent = cat;
        select.appendChild(opt);
      });
    }

    document.addEventListener("click", function (event) {
      if (!wrapper.contains(event.target)) {
        popoverPanel.classList.add("account-menu-hidden");
        resetToMain();
      }
    });

    document.addEventListener("keydown", function (event) {
      if (event.key === "Escape") {
        popoverPanel.classList.add("account-menu-hidden");
        resetToMain();
      }
    });

    if (avatarBtn) {
      avatarBtn.addEventListener("click", function (e) {
        e.stopPropagation();
        popoverPanel.classList.toggle("account-menu-hidden");
        if (popoverPanel.classList.contains("account-menu-hidden")) {
          resetToMain();
        }
      });
    }

    wrapper.querySelectorAll(".sub-frame-trigger-btn").forEach(function (btn) {
      btn.addEventListener("click", function (e) {
        e.stopPropagation();
        var target = btn.getAttribute("data-target-frame");
        populateCategoryDropdown(target);
        wrapper.querySelectorAll(".popover-frame").forEach(function (f) {
          f.classList.add("account-menu-hidden");
        });
        var targetFrame = wrapper.querySelector('.popover-frame[data-frame-id="' + target + '"]');
        if (targetFrame) targetFrame.classList.remove("account-menu-hidden");
      });
    });

    wrapper.querySelectorAll(".back-to-main-popover-btn").forEach(function (btn) {
      btn.addEventListener("click", function (e) {
        e.stopPropagation();
        resetToMain();
      });
    });

    function refreshAvatarImages(url) {
      document.querySelectorAll(".inner-popover-avatar-preview, #avatarImageGlobalDisplay").forEach(function (el) {
        if (el.tagName === "IMG") {
          el.src = url;
        } else {
          var img = document.createElement("img");
          img.src = url;
          img.className = el.className;
          img.alt = "Profile avatar";
          if (el.id) img.id = "avatarImageGlobalDisplay";
          img.classList.add("avatar-img");
          el.replaceWith(img);
        }
      });
    }

    if (uploadTrigger && fileInput) {
      uploadTrigger.addEventListener("click", function (e) {
        e.stopPropagation();
        fileInput.click();
      });
      fileInput.addEventListener("change", function () {
        if (!fileInput.files || fileInput.files.length === 0) return;
        var file = fileInput.files[0];
        if (file.size > 512 * 1024) {
          alert("File exceeds maximum size of 512 KB.");
          fileInput.value = "";
          return;
        }
        var formData = new FormData();
        formData.append("avatar", file);
        var headers = {};
        var csrf = getCsrfToken();
        if (csrf) headers["X-CSRFToken"] = csrf;
        fetch(config.avatar_post_url || "/auth/account/avatar", {
          method: "POST",
          body: formData,
          headers: headers,
          credentials: "same-origin",
        })
          .then(function (res) {
            return res.json().then(function (data) {
              return { ok: res.ok, data: data };
            });
          })
          .then(function (result) {
            if (result.ok && result.data.success) {
              refreshAvatarImages(result.data.avatar_url);
            } else {
              alert((result.data && result.data.error) || "Avatar upload failed.");
            }
            fileInput.value = "";
          })
          .catch(function (err) {
            console.error("avatar upload error", err);
            fileInput.value = "";
          });
      });
    }

    wrapper.querySelectorAll(".popover-nested-submission-form-element").forEach(function (form) {
      form.addEventListener("submit", function (e) {
        e.preventDefault();
        var kind = form.getAttribute("data-submission-kind");
        var submitBtn = form.querySelector(".submit-popover-form-action-btn");
        var payload = { kind: kind, page_url: window.location.href };
        var formData = new FormData(form);
        formData.forEach(function (value, key) {
          if (key === "beta_test") {
            payload[key] = form.querySelector('[name="beta_test"]')?.checked || false;
          } else {
            payload[key] = value;
          }
        });
        var originalText = submitBtn.textContent;
        submitBtn.disabled = true;
        submitBtn.textContent = "Sending...";
        var headers = { "Content-Type": "application/json" };
        var csrf = getCsrfToken();
        if (csrf) headers["X-CSRFToken"] = csrf;
        fetch(config.submission_post_url || "/auth/account/submissions", {
          method: "POST",
          headers: headers,
          body: JSON.stringify(payload),
          credentials: "same-origin",
        })
          .then(function (res) {
            return res.json().then(function (data) {
              return { ok: res.ok, data: data };
            });
          })
          .then(function (result) {
            if (result.ok && result.data.success) {
              submitBtn.classList.remove("menu-btn-primary");
              submitBtn.classList.add("menu-btn-success");
              submitBtn.textContent = "Thanks — we received your report";
              form.reset();
              setTimeout(function () {
                popoverPanel.classList.add("account-menu-hidden");
                resetToMain();
                submitBtn.classList.add("menu-btn-primary");
                submitBtn.classList.remove("menu-btn-success");
                submitBtn.textContent = originalText;
                submitBtn.disabled = false;
              }, 2000);
            } else {
              alert((result.data && result.data.error) || "Submission failed.");
              submitBtn.disabled = false;
              submitBtn.textContent = originalText;
            }
          })
          .catch(function (err) {
            console.error("submission error", err);
            submitBtn.disabled = false;
            submitBtn.textContent = originalText;
          });
      });
    });
  });
})();
