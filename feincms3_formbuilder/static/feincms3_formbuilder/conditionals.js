/*
 * Conditional form fields for feincms3-formbuilder.
 *
 * The server already rendered each field's correct initial state; this only
 * keeps it in sync as the user answers the controlling field. Without this
 * script the form still works — the server re-decides on every submit — so
 * nothing here may be load-bearing for correctness.
 */
(function () {
  "use strict";

  function controllingValue(form, name) {
    const inputs = form.querySelectorAll(
      'select[name="' + name + '"], input[type="radio"][name="' + name + '"]'
    );
    // Not on this page (another step): the server already decided, leave it.
    if (!inputs.length) return null;
    for (const input of inputs) {
      if (input.tagName === "SELECT") return input.value;
      if (input.checked) return input.value;
    }
    return "";
  }

  function apply(wrapper) {
    const form = wrapper.closest("form");
    if (!form) return;

    const value = controllingValue(form, wrapper.dataset.showWhenField);
    if (value === null) return;

    let values;
    try {
      values = JSON.parse(wrapper.dataset.showWhenValues || "[]");
    } catch (e) {
      return;
    }
    const active = values.indexOf(value) !== -1;

    wrapper.hidden = !active;
    for (const input of wrapper.querySelectorAll("input, select, textarea")) {
      if (active) {
        input.disabled = false;
        if (input.dataset.required !== undefined) {
          input.required = true;
          delete input.dataset.required;
        }
      } else {
        // Remember "required" so revealing the field restores the browser's
        // own validation; a hidden required input would block submission.
        if (input.required) {
          input.dataset.required = "true";
          input.required = false;
        }
        input.disabled = true;
      }
    }
  }

  function applyAll() {
    document.querySelectorAll("[data-show-when-field]").forEach(apply);
  }

  document.addEventListener("change", applyAll);
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", applyAll);
  } else {
    applyAll();
  }
})();
