# Conditional fields — design

Supersedes `2026-08-24-conditional-fields-design.md`, which kept fields in or
out of the Django form depending on where their controlling field sat. This
revision replaces that pair of mechanisms with a single one.

## Goal

Let editors configure fields that are only shown — and only required, when
configured required — depending on how another field is answered. The feature
must work in both the simple and multistep form paths and keep the package
thin and portable.

## Vocabulary

Two words, two referents, used consistently in the code and the README:

- A **condition** is the rule itself: a controlling field's name plus the
  values that satisfy it. A field *has* a condition.
- The **conditionals** are the fields that have one. A form *contains*
  conditionals.

## Core principle: the server renders its own truth

There is exactly one visibility rule and one mechanism:

> Given the data available at the moment a form is built, a field with a
> condition is *active* iff the controlling field's value satisfies the
> condition. Every conditional field is always part of the Django form.
> Inactive ones are rendered hidden, are not required, and their value is
> dropped before the form's data is used.

The rule is a pure function of two things: the conditions configured on the
plugins, and the data available right now. It never asks which step a field is
on, whether its controlling field is in the same form, or whether the browser
can see it.

Available data per path:

- simple form: the plugins' initial values on GET, the POST on submit
- multistep form: the accumulated session data, merged with the current POST
  when there is one

The initial values matter on GET: a controlling select with a `default_value`
is already answered before the user touches it, and its dependent field has to
render visible straight away rather than waiting for the script.

Consequences:

- A controlling value that is not in the available data (asked on a step not
  yet answered) reads as "no answer" → the field is inactive.
- Conditions across steps are decided entirely on the server and need no extra
  code path — the earlier step's answer is simply part of the available data.
- Navigating back in a multistep form, changing an answer, and coming forward
  re-evaluates each field the next time its form is built.
- Misconfigurations (unknown controlling field, controlling field on a later
  step, …) are reported to editors by an editor-time check. At runtime they
  make the field inactive and are logged.

### Why the field stays in the form

Removing an inactive field from the form is the obvious simplification and it
does not work, for two independent reasons:

- The browser must be able to reveal the field when the user changes the
  controlling answer in the same form. A field that is not rendered cannot be
  revealed.
- Without JavaScript, the server needs the field present on the next request
  to report it as missing (see below).

Keeping it and rendering the server's own decision costs less than the
alternative: `render_form_field` never has to guard against a plugin whose
fields are absent (`form.get_form_fields(plugin)` raises `KeyError`), and
nothing in `conditionals.py` needs to know the shape of the current form.

### Behaviour without JavaScript

Because the server renders its own decision rather than letting a script undo
it, a same-form condition degrades to one extra round-trip per branch:

1. GET: `contact_pref` is unanswered → the phone field is inactive → rendered
   hidden, not required.
2. The user picks "phone" and submits. The POST carries
   `contact_pref=phone` and no phone value.
3. The server rebuilds the form with the POST as available data → the phone
   field is now **active** → required, empty → a validation error.
4. The form re-renders with the phone field active, therefore visible, with
   "This field is required." and `contact_pref` still set to "phone".
5. The user fills it in and submits. Valid.

With JavaScript, steps 2–4 never happen because the script reveals the field
immediately. The script is a progressive enhancement that removes round-trips;
it does not enable the feature. Conditions across steps need no script at all.

## Scope

- **Controlling fields** are `SimpleField`s of type **select** or **radio**
  only. Other types (checkbox, multi-selects, free-text, date, integer) and
  custom plugins cannot control other fields.
- **Conditionals** can be of any type, as long as their plugin uses the mixin
  below. Plugins without the mixin are always unconditional.
- **One rule only:** the field is active iff the controlling field's answer is
  one of the configured values.
- **No chains:** a controlling field must not itself be conditional.
- **The condition belongs to the plugin, not to a single form field.** A
  compound plugin that generates several form fields hides, deactivates and
  drops all of them together.

Out of scope, and worth saying so because editors will run into it: a step on
which every field happens to be inactive still appears in the progress
indicator and renders as a step with nothing but a Next button. Skipping such
steps would pull in back-navigation and step-status changes and is not part of
this feature.

## Data model

Ship an abstract mixin in `models.py`; the project mixes it into its concrete
`SimpleField` and generates the migration (same opt-in pattern as the other
abstract models):

```python
class ConditionalFieldMixin(models.Model):
    show_when_field = models.CharField(max_length=50, blank=True)
    show_when_values = models.TextField(blank=True)  # one value per line

    class Meta:
        abstract = True

    @property
    def show_when_values_list(self):
        """Choice keys, parsed like feincms3-forms parses ``choices``."""
```

- `show_when_field` empty ⇒ unconditional (a normal field). Otherwise it holds
  the `name` of the controlling `SimpleField`. `max_length=50` matches
  feincms3-forms' `NameField`.
- `show_when_values` mirrors how feincms3-forms stores `choices` (a
  `TextField`, one value per line). Each line is parsed exactly like a
  `choices` line (`SimpleFieldBase.get_choices()` logic) and reduced to its
  key, so editors can enter the label (`Phone`), the key (`phone`) or a line
  copied from `choices` (`phone | Phone`). Python code and the rendered data
  attribute only ever use the parsed keys from `show_when_values_list`.
- Portable across all databases (no `ArrayField`).
- The name `show_when_values` (plural, but text) deliberately mirrors
  `choices`, which editors see next to it.

A `ForeignKey` to the controlling plugin would survive renames, but sibling
foreign keys inside one content-editor inline formset are awkward (unsaved
instances, ordering), and every other cross-field reference in feincms3-forms
— uniqueness validation, `{{ form_data.<name> }}` in notification recipients —
already goes by name.

## Evaluation

All condition logic lives in a new module, `conditionals.py`, which does not
depend on the views.

- **Reading the controlling value:** `data.get(name, "")` on the available data
  (POST `QueryDict`, session dict, or the merge of both). For select and radio
  the value is a single string in every source, empty when unanswered.
  `QueryDict.get()` returns the *last* value for a repeated key, which is why
  only single-valued controlling fields are supported; adding multi-selects
  later means reading `getlist()` where available.
- **The check:** a field is active iff it has no condition, or the controlling
  value is in `show_when_values_list`. An unanswered or missing controlling
  field is never a member.
- **Unsupported controlling field:** if the controlling field is among the
  plugins of the form being built but is not a select or radio, the field is
  inactive and a WARNING is logged (logger
  `feincms3_formbuilder.conditionals`). A controlling field that merely has no
  value yet is not logged — that is the ordinary cross-step case.

  A controlling field that exists in *no* region is not detected at runtime.
  Deciding that needs every region of the configured form, which the helper
  deliberately does not receive — giving it the form's shape is exactly the
  coupling this design removes. It is the editor-time check's job, where an
  editor can act on it; at runtime the field is simply never shown.

## Server enforcement

The server is the authority. Every place in `views.py` that builds a form goes
through **one helper** in `conditionals.py`, so no call site can drift from the
others:

```python
create_form_with_conditionals(
    plugins, *, form_class, form_kwargs, available_data=None
)
```

`plugins`, `form_class` and `form_kwargs` are passed straight through to
feincms3-forms' `create_form`; `available_data` is the only addition, and
nothing in feincms3-forms changes. It calls `create_form` first,
so that for an unbound form it can fall back to the merged `form.initial` as
the available data; that is where a controlling field's `default_value` lives.
Then, for every conditional plugin it finds inactive:

1. For each of that plugin's form fields: if `field.required`, set
   `field.widget.attrs["data-required"] = True` and then `field.required =
   False`. Set `field.widget.attrs["disabled"] = True`.
2. Record the inactive field names and the plugin's condition on
   `form._f3fb_conditionals`, a single namespace this package owns. The `_f3fb_`
   prefix mirrors feincms3-forms' `_f3f_` convention while staying out of its
   namespace; keeping it to one attribute keeps the two prefixes from
   interleaving.
3. Append a cleaner to `form._f3f_cleaners`, the list `create_form` already
   builds and `FormMixin.clean()` already runs — the one upstream attribute
   this package writes to, because appending to it is what it is for. The
   cleaner pops the inactive names from `cleaned_data` and from `form._errors`.

The condition is evaluated once, in the helper, from the available data — never
a second time from `cleaned_data`. For a same-form condition the two agree,
since the available data contains the submitted POST; keeping one source avoids
them ever disagreeing.

**Implementation trap:** set `field.widget.attrs["disabled"]`, *not*
`field.disabled = True`. Django's `disabled` form-field attribute makes the
field ignore submitted data in favour of `initial`, which silently breaks the
no-JavaScript round-trip above. Make sure this somehow survives the
implementation. Either by adding a comment, adding docs or adding a test that
covers this.

Errors are popped rather than prevented because `required` is checked in
`_clean_fields`, before `clean()` runs. Other validation (format, valid choice)
still runs on inactive fields, and its errors are popped along with the
required ones — an inactive field never blocks a submission.

### Call sites

When `available_data` is omitted the helper uses what the form already knows:
`form.data` when the form is bound, `form.initial` when it is not. That is
correct at every call site in `views.py` but one:

- `simple_form_view`, both branches — omit it.
- `_render_step` — omit it. The form is unbound with
  `initial={**accumulated_data, **_ref_initial(request)}`, and `create_form`
  merges the plugins' defaults *underneath* that, so a session answer correctly
  beats a `default_value`.
- `compute_step_statuses` and the final all-steps validation — omit it, both
  bind the form to `accumulated_data`.
- `multistep_form_view`, the current step's POST — **pass
  `accumulated_data | request.POST.dict()`.** `request.POST` carries only the
  current step's fields, and the controlling field may be on an earlier step.
  `.dict()` is not optional: a `QueryDict` subclasses `dict` but stores lists
  internally, so `accumulated_data | request.POST` would yield
  `{"name": ["Alice"]}`.

So the change to `views.py` is one import line, five renamed calls, and one
call gaining `available_data`.

### Dropping stale values on final submit

Values stay in `accumulated_data` while a conditional field is inactive, so
switching the controlling answer back restores the earlier input. They must not
reach `process`.

The all-steps validation loop that already runs on final submit builds a form
per step; collect each step form's inactive names from `_f3fb_conditionals`
there and, once every step is valid, filter `accumulated_data` with the union
before calling `process`. Only inactive conditional field names are removed;
other keys (e.g. `_ref`) stay.

This has to be a pass over all steps, not a removal when a single step is
submitted: a field on step 3 can become inactive because the user went back and
changed step 1, and step 1's form does not contain step 3's fields.

One cosmetic consequence: `compute_step_statuses`' `has_data` check can read a
step as non-empty on the strength of a value belonging to a now-inactive field.
Filter `form.fields` by the inactive names there if it proves confusing.

### Other consumers

- **Reporting / submissions:** inactive fields are absent from the stored
  `data`; existing formatting and report code needs no change.
- **Notifications:** a recipient written as `{{ form_data.<name> }}` that names
  an inactive field is skipped, exactly like an optional email field left empty
  today. No code change; documented in the README.

## Rendering contract

`render_form_field` asks `conditionals.condition_context(form, plugin)` for the
plugin's condition and passes it to `form_field.html`. The function returns
`{}` for unconditional plugins and otherwise the controlling field name, the
values as a JSON list of choice keys, and whether the plugin is currently
active. It is the documented entry point for projects with their own renderer.

```html
<div data-show-when-field="contact_pref"
     data-show-when-values='["phone","sms"]'
     hidden>
  …field…
</div>
```

- Unconditional fields emit no attributes and no `hidden`.
- The attributes are emitted whether or not the controlling field is in the
  same form. Deciding that is the script's job (it looks for the control and
  does nothing when it is absent), which keeps the Python side a pure function
  of conditions and data.
- `hidden` is present exactly when the server considers the plugin inactive.
  The browser's user-agent stylesheet hides it, so this works without
  JavaScript and without project CSS.
- Inputs of an inactive field carry `disabled` and, where the field would
  otherwise have been required, `data-required`.

## JavaScript (shipped)

Ship `static/feincms3_formbuilder/conditionals.js`: vanilla, dependency-free.
On load and on every `change` event, for each wrapper carrying
`data-show-when-field` it looks for a select or radio group with that name in
the same form and runs the same membership test as the server on its current
value.

- Active: remove `hidden` from the wrapper; for each input remove `disabled`
  and, if it carries `data-required`, set `required`.
- Inactive: for each input, if it is `required`, record `data-required` and
  clear `required`; set `disabled`. Set `hidden` on the wrapper.
- Controlling field not on the page (another step): leave the field alone, the
  server already decided.

Disabling the inputs matters in both directions: an input the script hides was
rendered by the server as active and therefore still carries the HTML
`required` attribute, which would block submission in the browser; and disabled
inputs are not submitted, which keeps the browser from sending values for
fields the user cannot see.

The project includes the script with one `<script>` tag, or supplies its own
using the documented contract. `pyproject.toml` already includes the whole
package folder in the build, so the file ships without extra configuration.

## Editor-time check

`validate_conditionals(configured_form, renderer)` in `conditionals.py`,
returning feincms3-forms `Error`s like `validate_notification_recipients`.
Projects call it from their form type's `validate` function; the admin shows
the errors after saving (a warning, not a block).

It loads the plugins with `contents_for_item`, as the views do, and collects
form field names, types, choices and regions from them. Rules for each
conditional field:

- the controlling field exists
- it is not the field itself
- it is a select or radio
- it is not conditional itself (no chains)
- it is on the same step as the conditional field, or an earlier one
- `show_when_values` is not empty, and every value is one of the controlling
  field's choice keys

The forward-reference rule is the one that only an editor-time check can catch:
at runtime a forward reference reads as "no answer", so the field is simply
never shown, with nothing to tell the editor why.

## Admin

`simple_field_inlines(model)` appends `show_when_field` and `show_when_values`
to each created inline's `advanced_fields` when the model uses
`ConditionalFieldMixin`. `SimpleFieldInline.create()` sets `advanced_fields`
with `setdefault`, so the appending happens on the returned inline class.
Projects building their inlines another way add the two fields themselves
(README note).

## Deliberately deferred (additive, no migration reshape)

- **Chained conditions** (A controls B controls C). Needs: the helper iterates
  the activity computation over all plugins until it stops changing, treating a
  field controlled by an inactive field as inactive; the JavaScript treats a
  disabled controlling input as empty and re-runs until stable; the chain rule
  is removed from the editor-time check.
- **Multi-select controlling fields** — nearly free: active if any selected
  value matches, read with `getlist()`.
- **Checkbox controlling fields** — not free: "is checked" is a different
  semantic from "value is one of", and there is no sensible choice key for an
  editor to type into `show_when_values`.
- **Negation** — an `invert` boolean giving "is not one of".
- **Multiple rules per field** (AND/OR across different controlling fields) —
  the only non-additive future step; would reshape storage.

## Iteration plan

Each slice is independently end-to-end testable and updates the README and
CHANGELOG in the same change.

1. **Simple form, complete.**
   - `ConditionalFieldMixin`, `show_when_values_list`
   - `conditionals.py`: reading the controlling value, the check,
     `create_form_with_conditionals`, `condition_context`, the WARNING log
   - `simple_form_view` through `create_form_with_conditionals`
   - `render_form_field` and `form_field.html`: data attributes, `hidden`
   - `conditionals.js`
   - admin wiring
   - README section "Conditional fields": setup (mixin, migration, admin), the
     vocabulary above, how editors configure a condition, including the script,
     the data attribute contract, what happens without JavaScript, limits
     (select/radio controlling fields only, no chains), the notification note

   Tested via the Django test client: a conditional required field is not
   required and renders hidden when its controlling field does not match, is
   required and visible when it does, a non-matching field's value never
   reaches the submission, and the no-JavaScript round-trip (submit with the
   controlling value set and the conditional field empty → the response carries
   a required error on that field); plus unit tests of the check (match, no
   match, unanswered, missing controlling field). JavaScript is verified
   manually in a browser; there is no JS test harness in this package.

2. **Multistep — same step and across steps together.** All multistep call
   sites (showing a step, submitting a step, step status indicators, final
   validation) through `create_form_with_conditionals`, with the current step's
   POST passing `accumulated_data | request.POST`; the union of the inactive
   names filtered out of `accumulated_data` before `process`.

   Tested: a same-step condition deactivates correctly; a cross-step condition
   is decided server-side with no script involved; going back, changing the
   controlling answer and submitting does not store the stale value; switching
   the answer back before submitting restores the earlier input. README:
   conditions across steps work without JavaScript and are re-evaluated on
   back/forward.

3. **Editor-time check.** `validate_conditionals` with all rules above. README:
   how to call it from the form type's `validate` function.
