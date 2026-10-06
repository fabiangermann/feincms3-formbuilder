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

  /*
   * The controlling field's answer as the server reads it, "" when unanswered,
   * or null when the field is not in this form and the server's decision
   * stands. The name is editor-typed free text, hence CSS.escape: a quote or
   * backslash would otherwise make the selector throw and stop every field.
   */
  function controllingValue(form, name) {
    const escaped = CSS.escape(name);
    const inputs = form.querySelectorAll(
      'select[name="' + escaped + '"], input[type="radio"][name="' + escaped + '"]'
    );
    // Not on this page (another step): the server already decided, leave it.
    if (!inputs.length) return null;
    for (const input of inputs) {
      if (input.tagName === "SELECT") return input.value;
      if (input.checked) return input.value;
    }
    return "";
  }

  /*
   * Bring one conditional in line with the current answer, toggling the
   * inputs as well as the wrapper: a hidden required input would block the
   * browser's submit, and a disabled one keeps its value from being sent.
   */
  function apply(wrapper) {
    const form = wrapper.closest("form");
    if (!form) return;

    const value = controllingValue(form, wrapper.dataset.showWhenField);
    if (value === null) return;

    let values;
    try {
      values = JSON.parse(wrapper.dataset.showWhenValues || "[]");
    } catch {
      return;
    }
    const active = values.indexOf(value) !== -1;

    wrapper.hidden = !active;
    for (const input of wrapper.querySelectorAll("input, select, textarea")) {
      input.required = active && "requiredIfActive" in input.dataset;
      input.disabled = !active;
    }
  }

  /*
   * The initial pass over every conditional on the page, which may hold
   * several forms.
   */
  function applyAll() {
    document.querySelectorAll("[data-show-when-field]").forEach(apply);
  }

  // Only the conditionals controlled by the changed input need re-evaluating.
  document.addEventListener("change", (event) => {
    const input = event.target;
    if (!input.form || !input.name) return;
    input.form
      .querySelectorAll('[data-show-when-field="' + CSS.escape(input.name) + '"]')
      .forEach(apply);
  });
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", applyAll);
  } else {
    applyAll();
  }
})();
