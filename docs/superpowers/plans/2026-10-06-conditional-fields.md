# Conditional fields Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let editors configure form fields that are only shown — and only required — when another field is answered a particular way, in both the simple and the multistep form path.

**Architecture:** One mechanism. Every conditional field is always part of the Django form; the server evaluates its condition against the data available at the moment the form is built, and renders inactive ones `hidden`, with `required` cleared, their inputs `disabled`, and their value dropped during `clean()`. A shipped vanilla script keeps that state in sync as the user changes the controlling field. Because the server renders its own decision rather than letting a script undo it, the feature works without JavaScript at the cost of one extra round-trip per branch.

**Tech Stack:** Django (4.2–6.0), feincms3, feincms3-forms ≥0.6, django-content-editor. Tests use Django's own test runner via `tests/manage.py`. No new dependencies.

**Spec:** `docs/superpowers/specs/2026-10-06-conditional-fields-design.md`

## Global Constraints

- **One branch per slice, prefix `conditionals/`:**
  - Tasks 1–7 → `conditionals/1-simple-form`
  - Tasks 8–9 → `conditionals/2-multistep`
  - Task 10 → `conditionals/3-editor-check`

  Each branch is created from the previous branch's final commit, because the slices build on each other. If an earlier branch has already been merged to `main` by the time you start the next, branch from `main` instead.
- **Commits are part of this plan.** The repository's normal rule is that the user runs all git commands; executing this plan overrides that for `git checkout -b`, `git add` and `git commit` on the three branches above. Do not merge, rebase, push, or touch `main`.
- **No new dependencies.** Everything ships with Django or is already in `pyproject.toml`.
- **Vocabulary, used consistently in code, comments and docs:** a **condition** is the rule (controlling field name + satisfying values); the **conditionals** are the fields that have one.
- **Naming:** module `feincms3_formbuilder/conditionals.py`; public names `create_form_with_conditionals`, `condition_context`, `validate_conditionals`, `ConditionalFieldMixin`; logger `feincms3_formbuilder.conditionals`; model fields `show_when_field`, `show_when_values`; form attribute `form._f3fb_conditionals` (the `_f3fb_` prefix mirrors feincms3-forms' `_f3f_` while staying out of its namespace).
- **Style:** ruff with the config in `pyproject.toml` (line length is not enforced, `FBT` is — no positional booleans). Every new function, method and class gets a short docstring saying why it exists, not restating its signature.
- **Test scope:** every test must be able to fail because of code in this repository. Do not test that Django validates a `CharField`, that a `ChoiceField` rejects an unknown choice, or that the ORM round-trips a value. Test our conditions, our form mutation, our rendering, and our view wiring.

---

## Development environment

The repository has no checked-in virtualenv; CI runs through tox. Create a local one once, at the start of Task 1 — `.venv/` is already in `.gitignore`.

```bash
uv venv
uv pip install -e ".[tests]" "Django>=5.2,<6.0"
```

Run tests with:

```bash
.venv/bin/python tests/manage.py test -v2 testapp
```

A single test case or method:

```bash
.venv/bin/python tests/manage.py test -v2 testapp.test_conditionals.IsActiveTest
```

---

## File structure

**New files**

| File | Responsibility |
|---|---|
| `feincms3_formbuilder/conditionals.py` | All condition logic: reading the controlling value, the active check, the form-building wrapper, the renderer's context helper, the editor-time check. Imports nothing from `views.py`. |
| `feincms3_formbuilder/static/feincms3_formbuilder/conditionals.js` | Keeps the rendered visibility state in sync with the controlling field while the page is open. |
| `tests/testapp/test_conditionals.py` | All tests for the above, plus the view-level tests for both form paths. |
| `tests/testapp/migrations/0007_*.py` | Adds the two mixin fields to the test app's `SimpleField`. Generated, not hand-written. |

**Modified files**

| File | Change |
|---|---|
| `feincms3_formbuilder/models.py` | Add `ConditionalFieldMixin` and the `_choice_key` helper. |
| `feincms3_formbuilder/renderer.py` | `render_form_field` passes the plugin's condition into the template. |
| `feincms3_formbuilder/templates/feincms3_formbuilder/form_field.html` | Emit the data attributes and `hidden`. |
| `feincms3_formbuilder/admin.py` | `simple_field_inlines` appends the two fields to each inline's `advanced_fields`. |
| `feincms3_formbuilder/views.py` | Build every form through `create_form_with_conditionals`; filter inactive values out of `accumulated_data` before `process`. |
| `tests/testapp/models.py` | Mix `ConditionalFieldMixin` into `SimpleField`. |
| `tests/testapp/validation.py` | Call `validate_conditionals` (Task 10). |
| `README.md`, `CHANGELOG.md` | Documentation, updated in the same change as the code it describes. |

---

# Branch `conditionals/1-simple-form`

```bash
git checkout main
git checkout -b conditionals/1-simple-form
```

---

### Task 1: The editor can configure a condition

Gives `SimpleField` the two configuration fields and surfaces them in the admin. Nothing reads them yet.

**Files:**
- Modify: `feincms3_formbuilder/models.py`
- Modify: `feincms3_formbuilder/admin.py:48-84` (`simple_field_inlines`)
- Modify: `tests/testapp/models.py:76-81` (`class SimpleField`)
- Create: `tests/testapp/migrations/0007_*.py` (generated)
- Create: `tests/testapp/test_conditionals.py`

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `feincms3_formbuilder.models.ConditionalFieldMixin` — abstract model with `show_when_field: str` and `show_when_values: str`, plus the property `show_when_values_list -> list[str]` returning choice keys.
  - `simple_field_inlines(model)` keeps its signature and return type (a list of 11 inline classes); each class's `advanced_fields` now ends with `"show_when_field", "show_when_values"` when `model` uses the mixin.

- [ ] **Step 1: Create the development virtualenv**

```bash
uv venv
uv pip install -e ".[tests]" "Django>=5.2,<6.0"
.venv/bin/python tests/manage.py test testapp 2>&1 | tail -5
```

Expected: the existing suite passes. If it does not, stop and report — this plan assumes a green baseline.

- [ ] **Step 2: Write the failing test**

Create `tests/testapp/test_conditionals.py`:

```python
from django.test import SimpleTestCase, TestCase

from feincms3_formbuilder.admin import simple_field_inlines
from feincms3_formbuilder.models import ConditionalFieldMixin
from testapp.models import SimpleField


class ShowWhenValuesListTest(SimpleTestCase):
    """The parsing must accept whatever an editor plausibly copies in.

    Editors see ``choices`` right next to ``show_when_values``, so they type
    the label, the key, or a whole ``key | Label`` line. All three have to
    reduce to the key the browser actually submits.
    """

    def test_label_key_and_pipe_lines_all_reduce_to_the_key(self):
        field = SimpleField(show_when_values="Phone\nsms\nemail | E-Mail")
        self.assertEqual(field.show_when_values_list, ["phone", "sms", "email"])

    def test_blank_lines_are_ignored(self):
        field = SimpleField(show_when_values="phone\n\n   \nsms\n")
        self.assertEqual(field.show_when_values_list, ["phone", "sms"])

    def test_no_values_is_an_empty_list(self):
        self.assertEqual(SimpleField().show_when_values_list, [])


class ConditionalAdminFieldsTest(TestCase):
    """Without this the two fields exist but no editor can reach them."""

    def test_inlines_expose_the_condition_fields(self):
        self.assertTrue(issubclass(SimpleField, ConditionalFieldMixin))
        for inline in simple_field_inlines(SimpleField):
            self.assertIn("show_when_field", inline.advanced_fields)
            self.assertIn("show_when_values", inline.advanced_fields)

    def test_existing_advanced_fields_are_kept(self):
        inline = simple_field_inlines(SimpleField)[0]
        self.assertIn("help_text", inline.advanced_fields)
```

- [ ] **Step 3: Run the test to verify it fails**

Run: `.venv/bin/python tests/manage.py test -v2 testapp.test_conditionals`
Expected: FAIL — `ImportError: cannot import name 'ConditionalFieldMixin'`.

- [ ] **Step 4: Add the mixin**

In `feincms3_formbuilder/models.py`, add `slugify` to the imports from `django.utils.text`:

```python
from django.utils.text import slugify
```

Then add, after `StepSlugField` and before `AbstractFormStep`:

```python
def _choice_key(line):
    """Reduce one ``choices``-style line to the key the browser submits.

    Mirrors ``SimpleFieldBase.get_choices()`` so that a line copied from
    ``choices`` into ``show_when_values`` resolves to the same key.
    """
    parts = [part.strip() for part in line.split("|", 1)]
    return parts[0] if len(parts) == 2 else slugify(line)


class ConditionalFieldMixin(models.Model):
    """Adds a show-when condition to a form field plugin.

    Mix into the project's concrete ``SimpleField`` and generate the
    migration. Plugins without the mixin are always unconditional, which is
    why every reader of a condition must tolerate the attributes being
    absent.
    """

    show_when_field = models.CharField(
        _("show when field"),
        max_length=50,
        blank=True,
        help_text=_(
            "Name of the dropdown or radio field controlling this field."
            " Leave empty to always show this field."
        ),
    )
    show_when_values = models.TextField(
        _("show when values"),
        blank=True,
        help_text=_(
            "One value per line. This field is shown when the controlling"
            " field's answer is one of them. Enter the label, the value, or a"
            " line copied from the controlling field's choices."
        ),
    )

    class Meta:
        abstract = True

    @property
    def show_when_values_list(self):
        """The condition's values as choice keys, in configured order."""
        return [
            _choice_key(line)
            for line in self.show_when_values.splitlines()
            if line.strip()
        ]
```

- [ ] **Step 5: Wire the mixin into the test app**

In `tests/testapp/models.py`, extend the import:

```python
from feincms3_formbuilder.models import (
    AbstractConfiguredForm,
    AbstractFormStep,
    AbstractFormSubmission,
    ConditionalFieldMixin,
)
```

and change the model declaration:

```python
class SimpleField(ConditionalFieldMixin, forms_models.SimpleFieldBase, ConfiguredFormPlugin):
    class Meta:
        verbose_name = "form field"
        verbose_name_plural = "form fields"
```

- [ ] **Step 6: Append the fields to the admin inlines**

In `feincms3_formbuilder/admin.py`, import the mixin:

```python
from feincms3_formbuilder.models import ConditionalFieldMixin
```

and replace the `return` at the end of `simple_field_inlines` with:

```python
    inlines = [
        forms_admin.SimpleFieldInline.create(
            model=proxy_model,
            button=icon,
            regions=deny_regions({"success"}),
        )
        for proxy_model, icon in type_configs
    ]

    if issubclass(model, ConditionalFieldMixin):
        for inline in inlines:
            # Assigning on the generated subclass; the base class's list must
            # stay untouched or every later call would grow it again.
            inline.advanced_fields = [
                *inline.advanced_fields,
                "show_when_field",
                "show_when_values",
            ]

    return inlines
```

Update the docstring's first line to mention that the condition fields are appended when the model uses `ConditionalFieldMixin`.

- [ ] **Step 7: Generate the migration**

```bash
.venv/bin/python tests/manage.py makemigrations testapp
```

Expected: one migration adding `show_when_field` and `show_when_values` to `testapp.simplefield`. Do not hand-edit it.

- [ ] **Step 8: Run the tests**

Run: `.venv/bin/python tests/manage.py test -v2 testapp`
Expected: PASS, including the pre-existing tests.

- [ ] **Step 9: Commit**

```bash
git add feincms3_formbuilder/models.py feincms3_formbuilder/admin.py \
        tests/testapp/models.py tests/testapp/migrations/ \
        tests/testapp/test_conditionals.py
git commit -m "feat: add ConditionalFieldMixin and surface it in the admin inlines"
```

---

### Task 2: Evaluating a condition

The pure logic: read the controlling answer out of whatever data is available, and decide whether a field applies. No forms involved.

**Files:**
- Create: `feincms3_formbuilder/conditionals.py`
- Modify: `tests/testapp/test_conditionals.py`

**Interfaces:**
- Consumes: `ConditionalFieldMixin.show_when_values_list` from Task 1.
- Produces:
  - `get_condition(plugin) -> tuple[str, list[str]] | None` — `(controlling field name, values)`, or `None` for an unconditional plugin.
  - `controlling_value(name, data) -> str` — the controlling answer, `""` when unanswered.
  - `is_active(condition, data) -> bool` — `True` when `condition` is `None`.
  - `CONTROLLING_TYPES: set[str]` — the `SimpleFieldBase.Type` values allowed to control other fields.
  - `logger` — `logging.getLogger("feincms3_formbuilder.conditionals")`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/testapp/test_conditionals.py`:

```python
from django.http import QueryDict

from feincms3_formbuilder.conditionals import (
    controlling_value,
    get_condition,
    is_active,
)
from testapp.models import SimpleField, Text


class GetConditionTest(SimpleTestCase):
    def test_no_controlling_field_means_unconditional(self):
        self.assertIsNone(get_condition(SimpleField(show_when_values="phone")))

    def test_plugin_without_the_mixin_is_unconditional(self):
        """Projects may register plugins that never heard of conditions."""

        class Plain:
            name = "plain"

        self.assertIsNone(get_condition(Plain()))

    def test_condition_is_the_name_and_the_parsed_keys(self):
        plugin = SimpleField(
            show_when_field="contact_pref", show_when_values="Phone\nsms"
        )
        self.assertEqual(get_condition(plugin), ("contact_pref", ["phone", "sms"]))


class ControllingValueTest(SimpleTestCase):
    def test_missing_key_reads_as_unanswered(self):
        self.assertEqual(controlling_value("contact_pref", {}), "")

    def test_none_reads_as_unanswered(self):
        self.assertEqual(controlling_value("contact_pref", {"contact_pref": None}), "")

    def test_querydict_yields_the_submitted_value(self):
        data = QueryDict("contact_pref=phone")
        self.assertEqual(controlling_value("contact_pref", data), "phone")

    def test_non_string_session_value_is_coerced(self):
        """Session data comes back through JSON and is not always a string."""
        self.assertEqual(controlling_value("count", {"count": 3}), "3")


class IsActiveTest(SimpleTestCase):
    condition = ("contact_pref", ["phone", "sms"])

    def test_unconditional_field_is_always_active(self):
        self.assertTrue(is_active(None, {}))

    def test_matching_answer_activates(self):
        self.assertTrue(is_active(self.condition, {"contact_pref": "phone"}))

    def test_other_answer_deactivates(self):
        self.assertFalse(is_active(self.condition, {"contact_pref": "email"}))

    def test_unanswered_controlling_field_deactivates(self):
        """This is also the cross-step case: a step not yet reached has no answer."""
        self.assertFalse(is_active(self.condition, {}))

    def test_condition_without_values_never_matches(self):
        self.assertFalse(is_active(("contact_pref", []), {"contact_pref": "phone"}))
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/python tests/manage.py test -v2 testapp.test_conditionals`
Expected: FAIL — `ModuleNotFoundError: No module named 'feincms3_formbuilder.conditionals'`.

- [ ] **Step 3: Create the module**

Create `feincms3_formbuilder/conditionals.py`:

```python
"""Conditional form fields for feincms3-formbuilder.

A *condition* is the rule configured on a field plugin: the name of a
controlling field plus the values that satisfy it.  The *conditionals* are the
fields that have one.

A conditional is active when the data available at the moment the form is built
satisfies its condition.  That is the whole rule: the logic never asks which
step a field is on, whether its controlling field is in the same form, or
whether the browser can see it.  An unanswered controlling field is simply not
a match, which is what makes conditions across steps work with no extra code.

Public API:

- ``create_form_with_conditionals`` — build a form with its conditionals
  resolved.
- ``condition_context`` — the template context a renderer needs to emit a
  condition as data attributes.
- ``validate_conditionals`` — editor-time check for the form type's
  ``validate`` function.
"""

import logging

from feincms3_forms.models import SimpleFieldBase


logger = logging.getLogger("feincms3_formbuilder.conditionals")

CONTROLLING_TYPES = {SimpleFieldBase.Type.SELECT, SimpleFieldBase.Type.RADIO}


def get_condition(plugin):
    """Return ``(controlling field name, values)``, or ``None`` if unconditional.

    Tolerates plugins without ``ConditionalFieldMixin``: a project may register
    field plugins that never opted into conditions.
    """
    name = getattr(plugin, "show_when_field", "")
    if not name:
        return None
    return (name, plugin.show_when_values_list)


def controlling_value(name, data):
    """Return the controlling field's answer as a string, ``""`` when unanswered.

    ``data`` may be a POST ``QueryDict``, the multistep session dict, or a
    merge of both; ``.get()`` behaves the same on all three for the
    single-valued select and radio fields that are allowed to control other
    fields.
    """
    value = data.get(name)
    return "" if value is None else str(value)


def is_active(condition, data):
    """Whether a field carrying ``condition`` applies to the available data.

    An unconditional field (``condition is None``) is always active; so is any
    caller that forgets to look one up.
    """
    if condition is None:
        return True
    name, values = condition
    return controlling_value(name, data) in values
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv/bin/python tests/manage.py test -v2 testapp.test_conditionals`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add feincms3_formbuilder/conditionals.py tests/testapp/test_conditionals.py
git commit -m "feat: add condition evaluation to a new conditionals module"
```

---

### Task 3: Building a form with its conditionals resolved

The wrapper around feincms3-forms' `create_form`. After this task a form knows which of its fields do not apply, has stopped requiring them, and drops their values during `clean()`.

**Files:**
- Modify: `feincms3_formbuilder/conditionals.py`
- Modify: `tests/testapp/test_conditionals.py`

**Interfaces:**
- Consumes: `get_condition`, `is_active`, `CONTROLLING_TYPES`, `logger` from Task 2.
- Produces:
  - `create_form_with_conditionals(plugins, *, form_class=forms.Form, form_kwargs, available_data=None) -> form` — `plugins`, `form_class` and `form_kwargs` go straight to `create_form`.
  - `form._f3fb_conditionals` — a `FormConditionals` instance with `.inactive: set[str]` (form field names) and `.conditions: dict[plugin, dict]`, each inner dict having keys `"field": str`, `"values": str` (a JSON array) and `"active": bool`.

**Why the field is not simply left out of the form:** the browser must be able to reveal it when the controlling answer changes in the same form, and without JavaScript the server needs it present on the next request to report it as missing.

- [ ] **Step 1: Write the failing tests**

Append to `tests/testapp/test_conditionals.py`:

```python
from feincms3_formbuilder.conditionals import create_form_with_conditionals
from testapp.models import ConfiguredForm, Radio


class ConditionalFormTestCase(TestCase):
    """Shared fixture: a radio control and a required text field depending on it.

    Holds no tests of its own — Task 4 reuses it, and subclassing a class that
    has tests would re-run them under every subclass's name.
    """

    def setUp(self):
        self.configured_form = ConfiguredForm.objects.create(
            name="Contact", slug="contact-build", form_type="simple",
        )
        self.control = Radio.objects.create(
            parent=self.configured_form, region="form", ordering=10,
            name="contact_pref", label="Preferred contact",
            is_required=True, choices="Phone\nEmail",
        )
        self.conditional = Text.objects.create(
            parent=self.configured_form, region="form", ordering=20,
            name="phone", label="Phone number", is_required=True,
            show_when_field="contact_pref", show_when_values="phone",
        )
        self.plugins = [self.control, self.conditional]

    def _form(self, data=None, **kwargs):
        return create_form_with_conditionals(
            self.plugins,
            form_kwargs={"data": data} if data is not None else {},
            **kwargs,
        )


class ConditionalFormBuildingTest(ConditionalFormTestCase):
    """The server is the authority: what it builds decides what is accepted."""

    def test_matching_answer_keeps_the_field_required(self):
        form = self._form({"contact_pref": "phone"})
        self.assertTrue(form.fields["phone"].required)
        self.assertNotIn("phone", form._f3fb_conditionals.inactive)
        self.assertFalse(form.is_valid())
        self.assertIn("phone", form.errors)

    def test_other_answer_clears_required_and_drops_the_value(self):
        form = self._form({"contact_pref": "email", "phone": "123"})
        self.assertFalse(form.fields["phone"].required)
        self.assertIn("phone", form._f3fb_conditionals.inactive)
        self.assertTrue(form.is_valid())
        self.assertNotIn("phone", form.cleaned_data)

    def test_inactive_field_cannot_block_submission(self):
        """Other validation still runs; its errors must not survive either.

        A client that submits garbage for a field the user was never shown
        would otherwise produce an error on an invisible field.
        """
        self.conditional.max_length = 3
        self.conditional.save()
        form = self._form({"contact_pref": "email", "phone": "far too long"})
        self.assertTrue(form.is_valid())
        self.assertNotIn("phone", form.cleaned_data)

    def test_inactive_inputs_are_disabled_and_remember_required(self):
        """``data-required`` is what lets the script restore native validation."""
        form = self._form({"contact_pref": "email"})
        attrs = form.fields["phone"].widget.attrs
        self.assertTrue(attrs["disabled"])
        self.assertTrue(attrs["data-required"])

    def test_active_field_carries_no_condition_attributes(self):
        form = self._form({"contact_pref": "phone"})
        self.assertNotIn("disabled", form.fields["phone"].widget.attrs)
        self.assertNotIn("data-required", form.fields["phone"].widget.attrs)

    def test_unbound_form_falls_back_to_initial(self):
        """A controlling select with a default value is answered before the
        user touches it, so its dependent field must render visible at once."""
        self.control.default_value = "Phone"
        self.control.save()
        form = self._form()
        self.assertEqual(form._f3fb_conditionals.inactive, set())

    def test_explicit_available_data_wins_over_the_form(self):
        """The multistep step POST needs this: the controlling answer lives in
        the session, not in the current step's POST."""
        form = self._form({}, available_data={"contact_pref": "phone"})
        self.assertTrue(form.fields["phone"].required)

    def test_unsupported_controlling_field_deactivates_and_logs(self):
        """Pointing at a text field silently shows nothing; the log is the only
        runtime symptom, so it has to carry the field names.

        The controlling field is a second plugin rather than a retyped first
        one: ``SimpleFieldBase.save()`` resets ``type`` from the proxy class,
        so assigning a different type and saving would not stick.
        """
        nickname = Text.objects.create(
            parent=self.configured_form, region="form", ordering=5,
            name="nickname", label="Nickname",
        )
        self.conditional.show_when_field = "nickname"
        with self.assertLogs("feincms3_formbuilder.conditionals", "WARNING") as logs:
            form = create_form_with_conditionals(
                [nickname, self.control, self.conditional],
                form_kwargs={"data": {"nickname": "anything"}},
            )
        self.assertIn("phone", form._f3fb_conditionals.inactive)
        self.assertIn("nickname", logs.output[0])

    def test_condition_is_exposed_for_the_renderer(self):
        form = self._form({"contact_pref": "email"})
        condition = form._f3fb_conditionals.conditions[self.conditional]
        self.assertEqual(condition["field"], "contact_pref")
        self.assertEqual(condition["values"], '["phone"]')
        self.assertFalse(condition["active"])
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/python tests/manage.py test -v2 testapp.test_conditionals`
Expected: FAIL — `ImportError: cannot import name 'create_form_with_conditionals'`.

- [ ] **Step 3: Implement the wrapper**

Extend the imports at the top of `feincms3_formbuilder/conditionals.py`:

```python
import dataclasses
import json
import logging

from django import forms
from feincms3_forms.models import FormFieldBase, SimpleFieldBase
from feincms3_forms.renderer import create_form
```

Append to the module:

```python
@dataclasses.dataclass
class FormConditionals:
    """What a built form knows about its conditionals.

    ``inactive`` holds form field names, not plugins, because that is what the
    cleaner and the stale-value filter in ``views.py`` work with; ``conditions``
    is keyed by plugin because that is what a renderer has in hand.
    """

    inactive: set
    conditions: dict


def _drop_inactive(form, data):
    """Remove inactive conditionals from ``cleaned_data`` and from the errors.

    Runs as a ``create_form`` cleaner, i.e. from ``clean()``. Errors are popped
    rather than prevented because ``required`` and the field validators run in
    ``_clean_fields()``, before ``clean()`` is reached. An inactive field must
    never block a submission — the user cannot see it to fix it.
    """
    for name in form._f3fb_conditionals.inactive:
        data.pop(name, None)
        form._errors.pop(name, None)
    return data


def create_form_with_conditionals(
    plugins, *, form_class=forms.Form, form_kwargs, available_data=None
):
    """Build the form for ``plugins`` with every conditional resolved.

    ``plugins``, ``form_class`` and ``form_kwargs`` go straight to
    feincms3-forms' ``create_form``; ``available_data`` is the only addition.
    Omit it and the form's own data is used — ``form.data`` when bound,
    ``form.initial`` when not — which is correct at every call site except a
    multistep step POST, where the controlling field may sit on an earlier step
    and only the session holds its answer.

    Inactive conditionals stay in the form. They are rendered hidden by the
    template, stop being required, carry ``disabled`` inputs, and lose their
    value in ``clean()``.
    """
    form = create_form(plugins, form_class=form_class, form_kwargs=form_kwargs)
    if available_data is None:
        available_data = form.data if form.is_bound else form.initial

    state = FormConditionals(inactive=set(), conditions={})
    form._f3fb_conditionals = state

    field_plugins = [p for p in plugins if isinstance(p, FormFieldBase)]
    types = {p.name: getattr(p, "type", "") for p in field_plugins}

    for plugin in field_plugins:
        condition = get_condition(plugin)
        if condition is None:
            continue
        name, values = condition
        if name in types and types[name] not in CONTROLLING_TYPES:
            # Only decidable for a controlling field in this very form; every
            # other misconfiguration is the editor-time check's job.
            logger.warning(
                "Field %r is controlled by %r, which is not a dropdown or a"
                " radio field. It will never be shown.",
                plugin.name,
                name,
            )
            active = False
        else:
            active = is_active(condition, available_data)

        state.conditions[plugin] = {
            "field": name,
            "values": json.dumps(values),
            "active": active,
        }
        if active:
            continue

        for field_name in form.get_form_fields(plugin):
            state.inactive.add(field_name)
            field = form.fields[field_name]
            if field.required:
                field.widget.attrs["data-required"] = True
                field.required = False
            field.widget.attrs["disabled"] = True

    if state.inactive:
        form._f3f_cleaners.append(_drop_inactive)
    return form
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv/bin/python tests/manage.py test -v2 testapp.test_conditionals`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add feincms3_formbuilder/conditionals.py tests/testapp/test_conditionals.py
git commit -m "feat: add create_form_with_conditionals"
```

---

### Task 4: Rendering the condition

The template emits the condition as data attributes and marks inactive fields `hidden`, so the rendered page matches the decision the server just made.

**Files:**
- Modify: `feincms3_formbuilder/conditionals.py`
- Modify: `feincms3_formbuilder/renderer.py:4-14`
- Modify: `feincms3_formbuilder/templates/feincms3_formbuilder/form_field.html`
- Modify: `tests/testapp/test_conditionals.py`

**Interfaces:**
- Consumes: `form._f3fb_conditionals` from Task 3.
- Produces: `condition_context(form, plugin) -> dict` — `{}` for an unconditional plugin or a form built without the wrapper, otherwise `{"field": str, "values": str, "active": bool}`. This is the documented entry point for projects with their own renderer.

- [ ] **Step 1: Write the failing tests**

Append to `tests/testapp/test_conditionals.py`:

```python
from django.template import Context
from feincms3_forms.renderer import create_form

from feincms3_formbuilder.conditionals import condition_context
from feincms3_formbuilder.renderer import render_form_field


class ConditionContextTest(ConditionalFormTestCase):
    def test_unconditional_plugin_has_no_context(self):
        form = self._form({"contact_pref": "phone"})
        self.assertEqual(condition_context(form, self.control), {})

    def test_form_built_without_the_wrapper_has_no_context(self):
        """Projects calling create_form directly must not crash the renderer."""
        form = create_form(self.plugins, form_kwargs={})
        self.assertEqual(condition_context(form, self.conditional), {})


class RenderFormFieldTest(ConditionalFormTestCase):
    def _render(self, plugin, data):
        form = self._form(data)
        return render_form_field(plugin, Context({"form": form}))

    def test_inactive_field_renders_hidden_with_the_attributes(self):
        html = self._render(self.conditional, {"contact_pref": "email"})
        self.assertIn('data-show-when-field="contact_pref"', html)
        self.assertIn("phone", html)
        self.assertIn("hidden", html)
        self.assertIn("disabled", html)

    def test_active_field_renders_visible(self):
        html = self._render(self.conditional, {"contact_pref": "phone"})
        self.assertIn('data-show-when-field="contact_pref"', html)
        self.assertNotIn("hidden", html)

    def test_unconditional_field_emits_no_attributes(self):
        html = self._render(self.control, {"contact_pref": "phone"})
        self.assertNotIn("data-show-when-field", html)
        self.assertNotIn("hidden", html)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/python tests/manage.py test -v2 testapp.test_conditionals`
Expected: FAIL — `ImportError: cannot import name 'condition_context'`.

- [ ] **Step 3: Add `condition_context`**

Append to `feincms3_formbuilder/conditionals.py`:

```python
def condition_context(form, plugin):
    """Return ``plugin``'s condition for a template, or ``{}``.

    Returns ``{}`` both for unconditional plugins and for forms built with
    feincms3-forms' ``create_form`` directly, so a project's own renderer works
    either way.
    """
    state = getattr(form, "_f3fb_conditionals", None)
    if state is None:
        return {}
    return state.conditions.get(plugin, {})
```

- [ ] **Step 4: Pass it into the template**

Replace `render_form_field` in `feincms3_formbuilder/renderer.py`:

```python
from feincms3.renderer import RegionRenderer, render_in_context

from feincms3_formbuilder.conditionals import condition_context


def render_form_field(plugin, context):
    """Render a form field plugin using the form object from context.

    ``condition`` carries the plugin's show-when rule so the template can emit
    it for the browser and hide the field when the server considers it
    inactive.
    """
    form = context.get("form")
    if not form:
        return ""
    fields = form.get_form_fields(plugin)
    return render_in_context(
        context,
        "feincms3_formbuilder/form_field.html",
        {
            "plugin": plugin,
            "fields": fields,
            "condition": condition_context(form, plugin),
        },
    )
```

- [ ] **Step 5: Emit the attributes**

Replace `feincms3_formbuilder/templates/feincms3_formbuilder/form_field.html`:

```html
{% for field in fields.values %}
<div
  {% if condition %}
    data-show-when-field="{{ condition.field }}"
    data-show-when-values='{{ condition.values }}'
    {% if not condition.active %}hidden{% endif %}
  {% endif %}
>
  {{ field.label_tag }}
  {{ field }}
  {% if field.help_text %}<p>{{ field.help_text }}</p>{% endif %}
  {{ field.errors }}
</div>
{% endfor %}
```

- [ ] **Step 6: Run the tests to verify they pass**

Run: `.venv/bin/python tests/manage.py test -v2 testapp`
Expected: PASS, including the existing `test_renderer.py` and `test_templatetags.py`.

- [ ] **Step 7: Commit**

```bash
git add feincms3_formbuilder/conditionals.py feincms3_formbuilder/renderer.py \
        feincms3_formbuilder/templates/feincms3_formbuilder/form_field.html \
        tests/testapp/test_conditionals.py
git commit -m "feat: render conditions as data attributes and hide inactive fields"
```

---

### Task 5: The simple form path

Wire `simple_form_view` through the wrapper. After this task the feature works end to end for a form without steps, with and without JavaScript.

**Files:**
- Modify: `feincms3_formbuilder/views.py:39-53`
- Modify: `tests/testapp/test_conditionals.py`

**Interfaces:**
- Consumes: `create_form_with_conditionals` from Task 3.
- Produces: no new names. `simple_form_view` keeps its signature.

- [ ] **Step 1: Write the failing tests**

Append to `tests/testapp/test_conditionals.py`:

```python
from django.urls import reverse

from testapp.models import FormSubmission, RichText


class ConditionalSimpleFormTest(TestCase):
    def setUp(self):
        self.configured_form = ConfiguredForm.objects.create(
            name="Contact", slug="contact-simple", form_type="simple",
        )
        Radio.objects.create(
            parent=self.configured_form, region="form", ordering=10,
            name="contact_pref", label="Preferred contact",
            is_required=True, choices="Phone\nEmail",
        )
        Text.objects.create(
            parent=self.configured_form, region="form", ordering=20,
            name="phone", label="Phone number", is_required=True,
            show_when_field="contact_pref", show_when_values="phone",
        )
        RichText.objects.create(
            parent=self.configured_form, region="success", ordering=10,
            text="<p>Thanks!</p>",
        )
        self.url = reverse("forms:form", kwargs={"slug": "contact-simple"})

    def test_first_get_hides_the_conditional_field(self):
        response = self.client.get(self.url)
        self.assertContains(response, 'data-show-when-field="contact_pref"')
        self.assertContains(response, "hidden")

    def test_matching_answer_without_the_value_is_rejected(self):
        """The no-JavaScript round-trip: the server asks for the field it
        would have revealed, instead of accepting a silently missing answer."""
        response = self.client.post(self.url, {"contact_pref": "phone"})
        self.assertNotContains(response, "Thanks!")
        self.assertEqual(FormSubmission.objects.count(), 0)
        self.assertContains(response, "This field is required.")

    def test_matching_answer_stores_the_value(self):
        response = self.client.post(
            self.url, {"contact_pref": "phone", "phone": "555-0100"}
        )
        self.assertContains(response, "Thanks!")
        self.assertEqual(
            FormSubmission.objects.get().data["phone"], "555-0100"
        )

    def test_other_answer_submits_without_the_field(self):
        response = self.client.post(self.url, {"contact_pref": "email"})
        self.assertContains(response, "Thanks!")
        self.assertNotIn("phone", FormSubmission.objects.get().data)

    def test_value_for_an_inactive_field_is_never_stored(self):
        """A client that submits it anyway must not get it into the database."""
        response = self.client.post(
            self.url, {"contact_pref": "email", "phone": "555-0100"}
        )
        self.assertContains(response, "Thanks!")
        self.assertNotIn("phone", FormSubmission.objects.get().data)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/python tests/manage.py test -v2 testapp.test_conditionals.ConditionalSimpleFormTest`
Expected: FAIL — `test_matching_answer_without_the_value_is_rejected` and `test_value_for_an_inactive_field_is_never_stored` fail, because `simple_form_view` still calls the plain `create_form`.

- [ ] **Step 3: Route the simple form through the wrapper**

In `feincms3_formbuilder/views.py`, add the import next to the existing one:

```python
from feincms3_forms.renderer import create_form

from feincms3_formbuilder.conditionals import create_form_with_conditionals
from feincms3_formbuilder.models import STEP_REGION_PREFIX
```

Then in `simple_form_view`, replace both `create_form(` calls with `create_form_with_conditionals(`, leaving every argument as it is:

```python
    if request.method == "POST":
        form = create_form_with_conditionals(
            contents["form"],
            form_class=form_class,
            form_kwargs={"data": request.POST, "files": request.FILES},
        )
        if form.is_valid():
            return configured_form.type.process(
                request, form, configured_form=configured_form
            )
    else:
        form = create_form_with_conditionals(
            contents["form"],
            form_class=form_class,
            form_kwargs={"initial": _ref_initial(request)},
        )
```

Neither passes `available_data`: the POST branch is bound, so `form.data` is `request.POST`; the GET branch is unbound, so `form.initial` carries the plugins' default values.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv/bin/python tests/manage.py test -v2 testapp`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add feincms3_formbuilder/views.py tests/testapp/test_conditionals.py
git commit -m "feat: resolve conditionals in the simple form view"
```

---

### Task 6: The shipped script

Keeps the rendered state in sync while the page is open, so a user with JavaScript never sees the extra round-trip.

**Files:**
- Create: `feincms3_formbuilder/static/feincms3_formbuilder/conditionals.js`

**Interfaces:**
- Consumes: the attributes emitted in Task 4 — `data-show-when-field`, `data-show-when-values`, `hidden`, and `disabled` / `data-required` on the inputs.
- Produces: nothing importable. There is no JavaScript test harness in this package; Step 3 verifies it in a browser.

- [ ] **Step 1: Write the script**

Create `feincms3_formbuilder/static/feincms3_formbuilder/conditionals.js`:

```javascript
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
```

- [ ] **Step 2: Include the script the way a project would**

The package templates must not hardcode the tag — the README tells projects to add it themselves, and doing it here would force `staticfiles` on every project. Override the two templates in the test app instead, which is also what exercises the documented integration.

First enable static files in `tests/testapp/settings.py` — add `"django.contrib.staticfiles"` to `INSTALLED_APPS` (after `"django.contrib.sessions"`), add `"django.template.context_processors.static"` to the template context processors, and add at the end of the file:

```python
STATIC_URL = "/static/"
```

Then copy `feincms3_formbuilder/templates/feincms3_formbuilder/form.html` to `tests/testapp/templates/feincms3_formbuilder/form.html` and `multistep_form.html` likewise, adding to each, just before the closing `</form>`:

```html
  {% load static %}
  <script src="{% static 'feincms3_formbuilder/conditionals.js' %}" defer></script>
```

These copies will drift from the package templates. That is acceptable: the package's own tests assert on the field markup the renderer produces, not on the form wrapper.

- [ ] **Step 3: Verify it in a browser**

```bash
.venv/bin/python tests/manage.py migrate
.venv/bin/python tests/manage.py createsuperuser
.venv/bin/python tests/manage.py runserver
```

In the admin, build a simple form with a radio field `contact_pref` (choices `Phone` / `Email`) and a required text field `phone` with `show_when_field=contact_pref`, `show_when_values=phone`. Then open the form page and confirm:

1. The phone field is not visible on load, and does not flash into view.
2. Picking "Phone" reveals it; the browser refuses to submit while it is empty.
3. Picking "Email" hides it again and the form submits.
4. With JavaScript disabled in the browser's devtools, picking "Phone" and submitting returns the page with the phone field visible and a required error on it.

- [ ] **Step 4: Run the test suite**

Run: `.venv/bin/python tests/manage.py test -v2 testapp`
Expected: PASS — the template change must not break the existing view tests.

- [ ] **Step 5: Commit**

```bash
git add feincms3_formbuilder/static/ tests/testapp/settings.py tests/testapp/templates/
git commit -m "feat: ship conditionals.js"
```

---

### Task 7: Documentation for the simple form slice

**Files:**
- Modify: `README.md` (new section after "Validation", before "Renderer")
- Modify: `CHANGELOG.md`

**Interfaces:**
- Consumes: everything from Tasks 1–6.
- Produces: nothing importable.

- [ ] **Step 1: Add the README section**

Insert a `## Conditional fields` section between the existing `## Validation` and `## Renderer` sections. Write it to cover, in this order:

1. **What it does, and the two words.** A *condition* is the rule configured on a field: the name of a controlling field plus the values that satisfy it. The *conditionals* are the fields that have one. A conditional is shown — and required, if configured required — only when the controlling field's answer is one of the configured values.

2. **Setup.** Mix `ConditionalFieldMixin` into the concrete `SimpleField` and generate the migration:

```python
from feincms3_formbuilder.models import ConditionalFieldMixin


class SimpleField(ConditionalFieldMixin, forms_models.SimpleFieldBase, ConfiguredFormPlugin):
    class Meta:
        verbose_name = "form field"
        verbose_name_plural = "form fields"
```

```bash
python manage.py makemigrations myapp
```

`simple_field_inlines()` adds the two fields to the "Advanced" fieldset of every inline on its own. Projects building their inlines another way append `"show_when_field"` and `"show_when_values"` to `advanced_fields` themselves.

3. **Including the script.**

```html
{% load static %}
<script src="{% static 'feincms3_formbuilder/conditionals.js' %}" defer></script>
```

4. **How editors configure a condition.** `show_when_field` holds the *name* of the controlling field. `show_when_values` takes one value per line; a line may be the label, the value, or a whole `value | Label` line copied from the controlling field's `choices`.

5. **Limits**, as a list: only dropdown and radio fields can control other fields; a controlling field must not itself be conditional; there is one rule per field.

6. **Without JavaScript.** State the round-trip plainly: the conditional field stays hidden until the user submits, the server then sees the controlling answer and returns the form with the field visible and a required error on it. Nothing is silently dropped.

7. **The data attribute contract**, for projects that want their own script. Show the rendered markup and say that `condition_context(form, plugin)` gives a custom renderer the same three values:

```html
<div data-show-when-field="contact_pref" data-show-when-values='["phone","sms"]' hidden>
  …field…
</div>
```

Say what the script must do, since the server's `required` handling depends on it: toggle `hidden` on the wrapper, toggle `disabled` on the inputs, and move `required` to and from `data-required`.

8. **Notifications.** A recipient written as `{{ form_data.<name> }}` naming an inactive field is skipped, exactly like an optional email field left empty.

- [ ] **Step 2: Add the changelog entry**

Insert above `## 0.4.0` in `CHANGELOG.md`:

```markdown
## Next version

### Features

- New `ConditionalFieldMixin` for the project's `SimpleField`, adding
  `show_when_field` and `show_when_values`. A field carrying a condition is
  only shown, only required and only stored when the controlling dropdown or
  radio field's answer is one of the configured values. The server decides and
  renders that decision, so the feature degrades to one extra round-trip
  without JavaScript rather than failing. Requires a migration in the project;
  see the README.
- New `feincms3_formbuilder/static/feincms3_formbuilder/conditionals.js`,
  included with one `<script>` tag, which keeps the rendered state in sync
  while the page is open. Projects may use the documented data attribute
  contract with their own script instead.
```

- [ ] **Step 3: Check the README renders and the links are right**

Run: `.venv/bin/python -c "import pathlib; print(pathlib.Path('README.md').read_text().count('## Conditional fields'))"`
Expected: `1`.

- [ ] **Step 4: Commit**

```bash
git add README.md CHANGELOG.md
git commit -m "docs: document conditional fields for the simple form"
```

---

# Branch `conditionals/2-multistep`

```bash
git checkout -b conditionals/2-multistep
```

---

### Task 8: The multistep path

Every multistep call site goes through the wrapper. Conditions within a step and conditions across steps both work after this task — the latter with no script involved, because the earlier step's answer is already in the session.

**Files:**
- Modify: `feincms3_formbuilder/views.py` — `compute_step_statuses` (86-120), `_render_step` (138-176), `multistep_form_view` (212-250)
- Modify: `tests/testapp/test_conditionals.py`

**Interfaces:**
- Consumes: `create_form_with_conditionals` from Task 3.
- Produces: `compute_step_statuses` gains a keyword-only `available_data=None` parameter; its other parameters and return value are unchanged. `_render_step` gains the same keyword-only parameter.

**The one trap:** `accumulated_data | request.POST` is wrong. `QueryDict` subclasses `dict` but stores lists internally, so `|` yields `{"name": ["Alice"]}`. Use `request.POST.dict()`, which returns the last value per key — exactly right for the single-valued select and radio fields that may control other fields.

- [ ] **Step 1: Write the failing tests**

Append to `tests/testapp/test_conditionals.py`:

```python
from testapp.models import FormStep


class ConditionalMultistepFormTest(TestCase):
    """Two steps: the controlling radio on step 1, the conditional on step 2.

    This is the case that needs no JavaScript at all — the server has the
    controlling answer in the session before it builds step 2.
    """

    def setUp(self):
        self.configured_form = ConfiguredForm.objects.create(
            name="Registration", slug="registration-cond", form_type="multistep",
        )
        self.step1 = FormStep.objects.create(
            configured_form=self.configured_form,
            title="Preference", identifier="pref", ordering=10,
        )
        self.step2 = FormStep.objects.create(
            configured_form=self.configured_form,
            title="Details", identifier="details", ordering=20,
        )
        Radio.objects.create(
            parent=self.configured_form, region=self.step1.region_key, ordering=10,
            name="contact_pref", label="Preferred contact",
            is_required=True, choices="Phone\nEmail",
        )
        Text.objects.create(
            parent=self.configured_form, region=self.step2.region_key, ordering=10,
            name="phone", label="Phone number", is_required=True,
            show_when_field="contact_pref", show_when_values="phone",
        )
        Text.objects.create(
            parent=self.configured_form, region=self.step2.region_key, ordering=20,
            name="note", label="Note", is_required=False,
        )
        RichText.objects.create(
            parent=self.configured_form, region="success", ordering=10,
            text="<p>Done!</p>",
        )
        self.url = reverse("forms:form", kwargs={"slug": "registration-cond"})

    def _post(self, data, action="next"):
        return self.client.post(self.url, {**data, "_action": action})

    def test_matching_earlier_answer_shows_the_field(self):
        response = self._post({"contact_pref": "phone"})
        self.assertContains(response, 'data-show-when-field="contact_pref"')
        self.assertNotContains(response, "hidden")

    def test_other_earlier_answer_hides_the_field(self):
        response = self._post({"contact_pref": "email"})
        self.assertContains(response, "hidden")

    def test_inactive_field_does_not_block_the_final_submit(self):
        self._post({"contact_pref": "email"})
        response = self._post({"note": "hi"}, action="submit")
        self.assertContains(response, "Done!")
        self.assertNotIn("phone", FormSubmission.objects.get().data)

    def test_active_field_is_required_on_the_final_submit(self):
        self._post({"contact_pref": "phone"})
        response = self._post({"note": "hi"}, action="submit")
        self.assertNotContains(response, "Done!")
        self.assertEqual(FormSubmission.objects.count(), 0)

    def test_going_back_and_changing_the_answer_drops_the_stale_value(self):
        """The value was valid when entered; a change on another step makes it
        inactive, and only a pass over every step before ``process`` sees that."""
        self._post({"contact_pref": "phone"})
        self._post({"phone": "555-0100"}, action="back")
        self._post({"contact_pref": "email"})
        response = self._post({"note": "hi"}, action="submit")
        self.assertContains(response, "Done!")
        self.assertNotIn("phone", FormSubmission.objects.get().data)

    def test_switching_the_answer_back_restores_the_earlier_input(self):
        """Values stay in the session while inactive, so a user who changes
        their mind twice does not have to type the answer again."""
        self._post({"contact_pref": "phone"})
        self._post({"phone": "555-0100"}, action="back")
        self._post({"contact_pref": "email"})
        self._post({}, action="back")
        self._post({"contact_pref": "phone"})
        response = self._post({"phone": "555-0100"}, action="submit")
        self.assertContains(response, "Done!")
        self.assertEqual(FormSubmission.objects.get().data["phone"], "555-0100")


class ConditionalSameStepTest(TestCase):
    """Controlling field and conditional on the same step: the browser decides
    live, but the server must still be the authority on what it accepts."""

    def setUp(self):
        self.configured_form = ConfiguredForm.objects.create(
            name="One step", slug="one-step-cond", form_type="multistep",
        )
        self.step = FormStep.objects.create(
            configured_form=self.configured_form,
            title="All", identifier="all", ordering=10,
        )
        Radio.objects.create(
            parent=self.configured_form, region=self.step.region_key, ordering=10,
            name="contact_pref", label="Preferred contact",
            is_required=True, choices="Phone\nEmail",
        )
        Text.objects.create(
            parent=self.configured_form, region=self.step.region_key, ordering=20,
            name="phone", label="Phone number", is_required=True,
            show_when_field="contact_pref", show_when_values="phone",
        )
        RichText.objects.create(
            parent=self.configured_form, region="success", ordering=10,
            text="<p>Done!</p>",
        )
        self.url = reverse("forms:form", kwargs={"slug": "one-step-cond"})

    def test_matching_answer_requires_the_field_in_the_same_post(self):
        response = self.client.post(
            self.url, {"contact_pref": "phone", "_action": "submit"}
        )
        self.assertNotContains(response, "Done!")
        self.assertContains(response, "This field is required.")

    def test_other_answer_submits_without_the_field(self):
        response = self.client.post(
            self.url, {"contact_pref": "email", "_action": "submit"}
        )
        self.assertContains(response, "Done!")
        self.assertNotIn("phone", FormSubmission.objects.get().data)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/python tests/manage.py test -v2 testapp.test_conditionals`
Expected: FAIL on the multistep cases — the multistep view still calls the plain `create_form`.

- [ ] **Step 3: Thread `available_data` through the multistep helpers**

In `feincms3_formbuilder/views.py`, change `compute_step_statuses`:

```python
def compute_step_statuses(
    contents, step_regions, accumulated_data, current_step, *, form_class,
    available_data=None,
):
    """
    Validate all steps against accumulated data to generate step statuses.

    Returns a list of dicts with keys: number, name, status, is_current.
    Status is one of: "empty", "valid", "invalid".

    ``available_data`` is what conditions are evaluated against; it defaults to
    ``accumulated_data``, which is right except while a step is being
    submitted, where the current POST has to be merged in first.
    """
    if available_data is None:
        available_data = accumulated_data
    steps = []
    for i, region in enumerate(step_regions):
        plugins = contents[region.key]
        if not accumulated_data:
            status = "empty"
        else:
            form = create_form_with_conditionals(
                plugins,
                form_class=form_class,
                form_kwargs={"data": accumulated_data},
                available_data=available_data,
            )
            has_data = any(accumulated_data.get(name) for name in form.fields)
            ...
```

Leave the rest of the function body as it is.

Then `_render_step`: add `available_data=None` to the keyword-only parameters, replace the `create_form` call, and pass the value on to `compute_step_statuses`:

```python
def _render_step(
    request, configured_form, contents, step_regions, step_index, accumulated_data,
    *, renderer, form_class, validation_form_class, extra_context=None,
    available_data=None,
):
    """Render a specific step, pre-filled with accumulated session data."""
    current_region = step_regions[step_index]
    total_steps = len(step_regions)

    form = create_form_with_conditionals(
        contents[current_region.key],
        form_class=form_class,
        form_kwargs={"initial": {**accumulated_data, **_ref_initial(request)}},
        available_data=available_data,
    )

    steps = compute_step_statuses(
        contents, step_regions, accumulated_data, step_index,
        form_class=validation_form_class,
        available_data=available_data,
    )
```

`_render_step` builds an unbound form, so leaving `available_data` at `None` makes the wrapper fall back to `form.initial` — which is `accumulated_data` merged over the plugins' defaults, so a session answer correctly beats a `default_value`. Callers that have a fresher POST pass it explicitly.

- [ ] **Step 4: Build the current step's form with the merged data**

In `multistep_form_view`, inside the `if request.method == "POST":` branch, replace the form creation:

```python
    if request.method == "POST":
        # The POST carries only this step's fields, but a controlling field may
        # live on an earlier one, so the session has to be merged in. Use
        # ``.dict()``: a QueryDict stores lists internally, so ``|`` would
        # produce ``{"name": ["Alice"]}``.
        available_data = accumulated_data | request.POST.dict()

        form = create_form_with_conditionals(
            contents[current_region.key],
            form_class=form_class,
            form_kwargs={"data": request.POST, "files": request.FILES},
            available_data=available_data,
        )
```

Then pass `available_data=available_data` to:

- the `_render_step(...)` call in the `going_back` branch
- the `_render_step(...)` call in the `next` branch
- the `compute_step_statuses(...)` call in the "validation failed" fallthrough at the end of the POST branch

and in the final all-steps validation loop, replace `create_form` with the wrapper:

```python
                for region in step_regions:
                    step_form = create_form_with_conditionals(
                        contents[region.key],
                        form_class=validation_form_class,
                        form_kwargs={"data": accumulated_data},
                        available_data=accumulated_data,
                    )
```

Note this loop uses `accumulated_data`, not the merged `available_data`: by the time it runs, `accumulated_data.update(form.cleaned_data)` has already folded the current step in, and it is the data `process` will receive.

The GET fall-through at the end of the function keeps calling `_render_step` without `available_data`.

Finally, remove the now-unused `from feincms3_forms.renderer import create_form` import if no call site is left.

- [ ] **Step 5: Run the tests**

Run: `.venv/bin/python tests/manage.py test -v2 testapp`
Expected: the rendering and same-step cases PASS; `test_going_back_and_changing_the_answer_drops_the_stale_value` still FAILS — nothing filters `accumulated_data` yet. That is Task 9.

- [ ] **Step 6: Commit**

```bash
git add feincms3_formbuilder/views.py tests/testapp/test_conditionals.py
git commit -m "feat: resolve conditionals at every multistep call site"
```

---

### Task 9: Dropping stale values before `process`

A value entered while its field was active stays in the session so that switching the controlling answer back restores it. It must not reach `process`.

**Files:**
- Modify: `feincms3_formbuilder/views.py` — the final validation loop in `multistep_form_view`
- Modify: `README.md`, `CHANGELOG.md`

**Interfaces:**
- Consumes: `step_form._f3fb_conditionals.inactive` from Task 3, the all-steps loop from Task 8.
- Produces: no new names.

**Why a pass over all steps:** a field on step 3 can become inactive because the user went back and changed step 1, and step 1's form does not contain step 3's fields. Removing values as each step is submitted cannot see that.

- [ ] **Step 1: Run the failing test**

Run: `.venv/bin/python tests/manage.py test -v2 testapp.test_conditionals.ConditionalMultistepFormTest.test_going_back_and_changing_the_answer_drops_the_stale_value`
Expected: FAIL — `"phone"` is still in the submission's data.

- [ ] **Step 2: Collect the inactive names and filter**

In `multistep_form_view`, extend the final validation loop and the block after it:

```python
                all_valid = True
                inactive = set()
                for region in step_regions:
                    step_form = create_form_with_conditionals(
                        contents[region.key],
                        form_class=validation_form_class,
                        form_kwargs={"data": accumulated_data},
                        available_data=accumulated_data,
                    )
                    inactive |= step_form._f3fb_conditionals.inactive
                    if not step_form.is_valid():
                        all_valid = False
                        break

                if all_valid:
                    # Values of fields that went inactive are kept in the
                    # session so switching the answer back restores them; this
                    # is the one place they must not survive.
                    accumulated_data = {
                        key: value
                        for key, value in accumulated_data.items()
                        if key not in inactive
                    }
                    # Clear session before processing
                    session_key = f"multistep_form_{configured_form.pk}"
                    request.session.pop(session_key, None)
                    return configured_form.type.process(
                        request, configured_form, accumulated_data
                    )
```

Only inactive conditional field names are removed; other keys (`_ref`, anything a project adds) stay.

- [ ] **Step 3: Run the tests**

Run: `.venv/bin/python tests/manage.py test -v2 testapp`
Expected: PASS, including `test_switching_the_answer_back_restores_the_earlier_input`, which proves the filter runs once at the end rather than per step.

- [ ] **Step 4: Document the multistep behaviour**

In the `## Conditional fields` README section, add a short "Multi-step forms" subsection saying:

- A condition may name a field on the same step or on an earlier one.
- A condition across steps is decided entirely on the server and needs no JavaScript.
- Going back and changing the controlling answer re-evaluates the condition the next time that step is built; the stale value is dropped on submit, and switching the answer back before submitting restores it.
- A field may only be controlled by a field on the same or an earlier step. A forward reference reads as "no answer", so the field is simply never shown — the editor-time check reports it (see the next section once Task 10 lands).
- A step on which every field happens to be inactive still appears in the progress indicator, as a step with nothing but a Next button. Put a conditional branch on a step that has other fields.

In `CHANGELOG.md`, extend the `## Next version` Features entry:

```markdown
- Conditions work in multi-step forms, within a step and across steps. A
  condition whose controlling field sits on an earlier step is resolved on the
  server and needs no JavaScript. Values of fields that became inactive are
  kept in the session — so changing the answer back restores them — and
  removed before `process` is called.
```

- [ ] **Step 5: Commit**

```bash
git add feincms3_formbuilder/views.py README.md CHANGELOG.md
git commit -m "feat: drop inactive conditionals from the multistep data before processing"
```

---

# Branch `conditionals/3-editor-check`

```bash
git checkout -b conditionals/3-editor-check
```

---

### Task 10: The editor-time check

At runtime a misconfigured condition just means the field is never shown, with nothing to tell the editor why. This is the only thing that catches a forward reference, a typo in the field name, or a value that is not one of the controlling field's choices.

**Files:**
- Modify: `feincms3_formbuilder/conditionals.py`
- Modify: `tests/testapp/validation.py`
- Modify: `tests/testapp/test_conditionals.py`
- Modify: `README.md`, `CHANGELOG.md`

**Interfaces:**
- Consumes: `get_condition`, `CONTROLLING_TYPES` from Task 2.
- Produces: `validate_conditionals(configured_form, renderer) -> list[Error]` — feincms3-forms `Error` instances, in the same shape as `validate_notification_recipients`. Projects call it from their form type's `validate` function; the admin shows the results as messages after saving, which warn rather than block.

- [ ] **Step 1: Write the failing tests**

Append to `tests/testapp/test_conditionals.py`:

```python
from feincms3_formbuilder.conditionals import validate_conditionals
from testapp.renderer import renderer


class ValidateConditionalsTest(TestCase):
    def setUp(self):
        self.configured_form = ConfiguredForm.objects.create(
            name="Checked", slug="checked", form_type="simple",
        )
        self.control = Radio.objects.create(
            parent=self.configured_form, region="form", ordering=10,
            name="contact_pref", label="Preferred contact",
            is_required=True, choices="Phone\nEmail",
        )

    def _conditional(self, **kwargs):
        return Text.objects.create(
            parent=self.configured_form, region="form", ordering=20,
            name="phone", label="Phone number", **kwargs,
        )

    def _errors(self):
        return [str(error) for error in validate_conditionals(
            self.configured_form, renderer
        )]

    def test_valid_condition_passes(self):
        self._conditional(show_when_field="contact_pref", show_when_values="Phone")
        self.assertEqual(self._errors(), [])

    def test_unconditional_fields_pass(self):
        self._conditional()
        self.assertEqual(self._errors(), [])

    def test_unknown_controlling_field_is_reported(self):
        self._conditional(show_when_field="nope", show_when_values="phone")
        self.assertIn("nope", self._errors()[0])

    def test_self_reference_is_reported(self):
        self._conditional(show_when_field="phone", show_when_values="phone")
        self.assertEqual(len(self._errors()), 1)

    def test_unsupported_controlling_type_is_reported(self):
        Text.objects.create(
            parent=self.configured_form, region="form", ordering=5,
            name="nickname", label="Nickname",
        )
        self._conditional(show_when_field="nickname", show_when_values="x")
        self.assertIn("nickname", self._errors()[0])

    def test_chained_condition_is_reported(self):
        self.control.show_when_field = "other"
        self.control.save()
        self._conditional(show_when_field="contact_pref", show_when_values="phone")
        self.assertTrue(any("contact_pref" in e for e in self._errors()))

    def test_empty_values_are_reported(self):
        self._conditional(show_when_field="contact_pref", show_when_values="")
        self.assertEqual(len(self._errors()), 1)

    def test_value_outside_the_controlling_choices_is_reported(self):
        self._conditional(show_when_field="contact_pref", show_when_values="fax")
        self.assertIn("fax", self._errors()[0])

    def test_controlling_field_on_a_later_step_is_reported(self):
        """At runtime a forward reference reads as "no answer", so the field is
        silently never shown. Only this check can tell the editor."""
        multistep = ConfiguredForm.objects.create(
            name="Steps", slug="steps-check", form_type="multistep",
        )
        first = FormStep.objects.create(
            configured_form=multistep, title="One", identifier="one", ordering=10,
        )
        second = FormStep.objects.create(
            configured_form=multistep, title="Two", identifier="two", ordering=20,
        )
        Radio.objects.create(
            parent=multistep, region=second.region_key, ordering=10,
            name="later_pref", label="Later", choices="Phone\nEmail",
        )
        Text.objects.create(
            parent=multistep, region=first.region_key, ordering=10,
            name="early", label="Early",
            show_when_field="later_pref", show_when_values="phone",
        )
        errors = [str(e) for e in validate_conditionals(multistep, renderer)]
        self.assertIn("later_pref", errors[0])
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/python tests/manage.py test -v2 testapp.test_conditionals`
Expected: FAIL — `ImportError: cannot import name 'validate_conditionals'`.

- [ ] **Step 3: Implement the check**

Extend the imports in `feincms3_formbuilder/conditionals.py`:

```python
from content_editor.contents import contents_for_item
from django.utils.translation import gettext as _
from feincms3_forms.validation import Error
```

`gettext`, not `gettext_lazy`: the messages are built and shown within one request, which is what `feincms3_forms.validation` does too.

Append to the module:

```python
def validate_conditionals(configured_form, renderer):
    """Report misconfigured conditions to the editor after saving.

    Returns feincms3-forms ``Error`` instances for the form type's ``validate``
    function, like ``validate_notification_recipients``. At runtime a
    misconfigured condition simply never matches, so the field is never shown
    and nothing explains why — which is what makes this check worth the code.
    """
    contents = contents_for_item(configured_form, plugins=renderer.plugins())
    region_order = {region.key: index for index, region in enumerate(configured_form.regions)}

    plugins = []
    for region in configured_form.regions:
        for plugin in contents[region.key]:
            if isinstance(plugin, FormFieldBase):
                plugins.append(plugin)
    by_name = {plugin.name: plugin for plugin in plugins}

    errors = []
    for plugin in plugins:
        condition = get_condition(plugin)
        if condition is None:
            continue
        name, values = condition

        if name == plugin.name:
            errors.append(Error(
                _("Field '%(field)s' is configured to depend on itself.")
                % {"field": plugin.name}
            ))
            continue

        control = by_name.get(name)
        if control is None:
            errors.append(Error(
                _("Field '%(field)s' depends on '%(control)s', which doesn't exist.")
                % {"field": plugin.name, "control": name}
            ))
            continue

        if getattr(control, "type", "") not in CONTROLLING_TYPES:
            errors.append(Error(
                _(
                    "Field '%(field)s' depends on '%(control)s', which is not a"
                    " dropdown or a radio field."
                )
                % {"field": plugin.name, "control": name}
            ))
            continue

        if get_condition(control) is not None:
            errors.append(Error(
                _(
                    "Field '%(field)s' depends on '%(control)s', which is itself"
                    " conditional. Chained conditions are not supported."
                )
                % {"field": plugin.name, "control": name}
            ))

        if region_order.get(control.region, 0) > region_order.get(plugin.region, 0):
            errors.append(Error(
                _(
                    "Field '%(field)s' depends on '%(control)s', which is asked on"
                    " a later step. It would never be shown."
                )
                % {"field": plugin.name, "control": name}
            ))

        if not values:
            errors.append(Error(
                _("Field '%(field)s' has a controlling field but no values.")
                % {"field": plugin.name}
            ))
            continue

        choice_keys = {key for key, _label in control.get_choices()}
        if unknown := [value for value in values if value not in choice_keys]:
            errors.append(Error(
                _(
                    "Field '%(field)s' is shown for %(values)s, which"
                    " '%(control)s' doesn't offer."
                )
                % {
                    "field": plugin.name,
                    "control": name,
                    "values": ", ".join(f"'{value}'" for value in sorted(unknown)),
                }
            ))

    return errors
```

- [ ] **Step 4: Call it from the test app**

In `tests/testapp/validation.py`:

```python
from feincms3_formbuilder.conditionals import validate_conditionals
from feincms3_formbuilder.models import validate_with_renderer
from feincms3_formbuilder.notifications import validate_notification_recipients
from testapp.renderer import renderer


def validate_configured_form(configured_form):
    return [
        *validate_with_renderer(configured_form, renderer),
        *validate_notification_recipients(
            configured_form, renderer, configured_form.notifications.all(),
        ),
        *validate_conditionals(configured_form, renderer),
    ]
```

- [ ] **Step 5: Run the tests**

Run: `.venv/bin/python tests/manage.py test -v2 testapp`
Expected: PASS.

- [ ] **Step 6: Document it**

Add an "Editor-time check" subsection to the `## Conditional fields` README section, after the limits:

```python
# myapp/validation.py
from feincms3_formbuilder.conditionals import validate_conditionals


def validate_configured_form(configured_form):
    return [
        *validate_with_renderer(configured_form, renderer),
        *validate_conditionals(configured_form, renderer),
    ]
```

List what it reports: an unknown controlling field, a self-reference, a controlling field that is not a dropdown or radio, a chained condition, a controlling field on a later step, a missing value list, and a value the controlling field does not offer. Say that the admin shows these as messages after saving — they warn, they do not block — and that a forward reference is the one failure with no runtime symptom at all, since the field is simply never shown.

In `CHANGELOG.md`, extend the `## Next version` Features entry:

```markdown
- New `validate_conditionals(configured_form, renderer)` for the form type's
  `validate` function. It reports conditions naming a field that doesn't
  exist, isn't a dropdown or radio, is itself conditional, or is asked on a
  later step, as well as empty or unknown value lists. Projects must add the
  call to their `validate` function (see README).
```

- [ ] **Step 7: Run the full suite one last time**

```bash
.venv/bin/python tests/manage.py test -v2 testapp
```

Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add feincms3_formbuilder/conditionals.py tests/testapp/validation.py \
        tests/testapp/test_conditionals.py README.md CHANGELOG.md
git commit -m "feat: add validate_conditionals for editor-time checking"
```

---

## Deliberately not built

From the spec's deferred list — do not add these without a new requirement:

- Chained conditions (A controls B controls C).
- Checkbox or multi-select controlling fields.
- Negation (`invert`).
- Multiple rules per field.
- Skipping a step on which every field is inactive.
