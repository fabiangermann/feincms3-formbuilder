# Architecture

## Bird's eye view

feincms3-formbuilder is a Django app for building forms that editors put
together in the Django admin. It is built on two lower-level libraries:

- django-content-editor stores a form's fields as plugins, ordered within
  regions.
- feincms3-forms turns those plugins into a Django form.

This package adds the parts every form-builder project would otherwise write
itself: abstract models, the views that show and submit forms (single-page and
multi-step), helpers for storing submissions, admin classes, and templates.

A form is a `ConfiguredForm` whose regions hold field plugins. The package
renders it and validates submissions; what happens to valid data is up to the
project's `process` function.

The package defines no concrete models. A project subclasses the abstract
models, registers its plugins with a renderer, and writes a view: either a
thin one that dispatches to the ready-made `simple_form_view` or
`multistep_form_view`, or its own. The README walks through the setup with the
ready-made views.

## Entry points

- **Rendering and submitting a form:** the project's view, either its own or
  one of the two ready-made ones in `views.py`, builds the form (through
  `conditionals` if the form uses conditional fields), renders the plugins
  through the project's renderer, and on a valid submission calls the
  `process` function configured on the form type.
- **Editing a form:** the project's `ModelAdmin` uses the inlines from
  `admin.py`. After the editor saves, feincms3-forms calls the form type's
  `validate` function, which the project assembles from the `validate_*`
  helpers in this package.
- **Startup:** `FeinCMS3FormbuilderConfig.ready()` in `apps.py` checks that the
  dotted paths in the package's settings can be imported.

## Codemap

Listed in dependency order: each component depends only on the ones above it.

### `models`

Defines the abstract models a project subclasses: `AbstractConfiguredForm`,
`AbstractFormStep`, `AbstractFormSubmission`, and `ConditionalFieldMixin` for
field plugins.

**Design note:** a multi-step form's steps are content-editor regions, one per
`FormStep` row. Each step's region key is `STEP_REGION_PREFIX` plus the step's
`identifier`.

Responsibilities:

- `AbstractConfiguredForm`: declares the default `simple` and `multistep` form
  types in `FORMS`, which projects override to point `validate` and `process`
  at their own functions.
- `AbstractFormSubmission`: stores the submitted data and an optional generic
  foreign key to a related object; `get_formatted_data` formats the data for
  display.
- `validate_with_renderer`: checks that field names are unique across all of
  the renderer's plugins.

Depends on feincms3-forms (`ConfiguredForm`, `FormType`, `validate_uniqueness`,
`simple_report`), django-content-editor (`Region`), django-admin-ordering
(`OrderableModel`).

**Architecture Invariant:** the package ships no concrete models and no
migrations. Projects own the tables, because every foreign key points at the
project's own `ConfiguredForm`.

### `processing`

Provides the helpers a project's `process` function uses to store a submission
and answer the request.

Responsibilities:

- `create_submission`: stores a submission with the client's IP address and
  user agent, and the related object resolved from the signed `_ref` token.
- `get_client_ip`: reads `REMOTE_ADDR`, or calls the project's
  `FORMBUILDER_CLIENT_IP_RESOLVER`.
- `render_success_region`: renders the form's `success` region as the response.

### `notifications`

Sends the emails configured on a form after a submission.

Responsibilities:

- `AbstractFormNotification` and `validate_recipients`: the model and the
  field validator for the recipient syntax.
- `send_form_notifications`: renders subject, body and recipients as Django
  templates against a context dict and sends one email per notification.
- `validate_notification_recipients`: the save-time configuration check that
  each `{{ form_data.<name> }}` recipient names an email field.

Depends on feincms3-forms (`SimpleFieldBase`, `Error`), html2text.

**Architecture Invariant:** nothing in the package sends email by itself; no
view, model or processing helper triggers a notification. The project decides
whether, when and how notifications go out. A common way is calling
`send_form_notifications` from its `process` function, but a background task
or the project's own mail code (e.g. a queue like django-mailer) work just as
well.

### `conditionals`

Adds conditional fields: fields that are shown, required and stored only when
a dropdown or radio field (the *controlling field*) has one of the configured
answers. Optional: a project opts in by adding `ConditionalFieldMixin` to its field
plugin.

**Design note:** the server makes the decision on every request.
`static/feincms3_formbuilder/conditionals.js` only keeps the page in sync
while the user changes answers.

Responsibilities:

- `create_form_with_conditionals`: wraps feincms3-forms' `create_form`. It
  marks inactive fields as not required and disabled, and drops their values
  and errors in `clean()`.
- `condition_context`: gives a renderer one plugin's condition. The template
  emits it as data attributes, which `conditionals.js` (or a project's own
  script) reads to show and hide the field in the browser.
- `validate_conditionals`: the save-time configuration check for
  misconfigured conditions.

Depends on models (`ConditionalFieldMixin`), feincms3-forms (`create_form`,
`FormFieldBase`, `SimpleFieldBase`, `Error`, and the form's `_f3f_cleaners`
list).

**Architecture Invariant:** whether a field is active depends only on the data
available when the form is built, never on which step a field is on. An
unanswered controlling field does not match, which is all that conditions
across steps need.

**Architecture Invariant:** the server alone decides which conditional fields
are active, so a submission without `conditionals.js` still produces a correct
result. Without the script the form needs an extra round trip: a required
conditional field only appears after the first submit, with an error asking
for it. The script only spares the user that round trip; nothing in it may be
needed for a correct result.

**API Boundary:** a view serving forms with conditional fields must build them
with `create_form_with_conditionals`; with feincms3-forms' `create_form`,
conditional fields are always shown and required, without any error. A
multi-step view must also pass the answers from earlier steps as
`available_data`, or conditions across steps never match. Forms without
conditional fields can use either function.

### `renderer`

Builds the `RegionRenderer` that turns a region's plugins into HTML.
`create_form_renderer` registers every field plugin with `render_form_field`,
which renders `form_field.html` with the field's condition.

Depends on conditionals (`condition_context`), feincms3 (`RegionRenderer`).

### `views`

Provides ready-made views for two common cases: `simple_form_view` for
single-page forms and `multistep_form_view` for forms split into steps.
Projects with other needs write their own views from the same parts.

**Design note:** the views return HTML fragments, not full pages: the
templates render only the `<form>` element, and the success response is the
bare `success` region. The embedding page loads them, for example with htmx.

**Design note:** a multi-step form keeps its answers in the session until the
final submit. Values of fields that became inactive are kept there too, so
switching an answer back restores them; they are filtered out only right
before `process` is called.

Depends on conditionals (`create_form_with_conditionals`), models
(`STEP_REGION_PREFIX`).

**API Boundary:** the views never choose a form type or look up a
`ConfiguredForm`; the project's own view does both and passes the
`ConfiguredForm` in.

### `admin` and `reporting`

Provides the admin building blocks a project registers itself: the
`FormStepInline`, one field inline per field type, `BaseFormSubmissionAdmin`,
and an XLSX export action. The package registers no `ModelAdmin` itself.

Responsibilities:

- `simple_field_inlines`: one inline per field type, kept out of the `success`
  region, with the condition fields added when the model uses
  `ConditionalFieldMixin`.
- `make_export_action` and `reporting.build_submissions_xlsx`: export
  submissions to one sheet per form.

Depends on models (`ConditionalFieldMixin`), feincms3-forms (`admin`,
`get_loaders`), django-admin-ordering, xlsxdocument (optional, `xlsx` extra).

### `templatetags` and `templates`

The `make_submission_ref` filter signs a reference to an object, which
`processing.create_submission` later resolves into the submission's related
object. The templates (`form.html`, `multistep_form.html`, `form_field.html`)
are minimal and meant to be overridden.

**API Boundary:** a project overriding `form_field.html` must emit the
`condition` as the shipped template does: the data attributes plus `hidden`.
`conditionals.js` and the server's no-JavaScript fallback both rely on that
markup.

## Cross-cutting concerns

- **Save-time configuration checks:** checks that need the whole form, such as
  `validate_with_renderer`, `validate_notification_recipients` and
  `validate_conditionals`, return feincms3-forms `Error` objects. The project
  combines them in its form type's `validate` function, and the admin shows
  them after saving without blocking the save.
- **Settings:** `FORMBUILDER_FROM_EMAIL` and `FORMBUILDER_CLIENT_IP_RESOLVER`,
  both optional. `apps.py` imports the resolver once at startup, so a wrong
  path fails at deploy time instead of on the first submission.
- **Logging:** `notifications` and `conditionals` log configuration problems
  that only show up at runtime, under `feincms3_formbuilder.<module>`.
- **Translations:** user-facing strings use `gettext`; catalogues for `de`
  and `fr` live in `locale/`.
- **Testing:** `tests/testapp` is a minimal project that subclasses the
  abstract models the way the README describes; the tests run against it
  through `tox` (`tests/manage.py test`).
