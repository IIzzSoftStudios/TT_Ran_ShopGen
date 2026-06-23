(function () {
  if (new URLSearchParams(window.location.search).get("embed") !== "1") {
    return;
  }
  document.documentElement.classList.add("gm-embed-root");

  function attachEmbedFields() {
    document.querySelectorAll('form[method="post"], form[method="POST"]').forEach(function (form) {
      if (form.querySelector('input[name="embed"]')) {
        return;
      }
      var input = document.createElement("input");
      input.type = "hidden";
      input.name = "embed";
      input.value = "1";
      form.appendChild(input);
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", attachEmbedFields);
  } else {
    attachEmbedFields();
  }
})();
