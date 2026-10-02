# Changelog

## 0.4.0

### Backwards incompatible changes

- `recipients` only accepts email addresses and plain
  `{{ form_data.<field_name> }}` variables. Filters, tags and other context
  variables are rejected on save, and at send time such a recipient is skipped
  and logged like an invalid address. The variables are looked up directly
  instead of rendering a template, so a submitted value containing commas can
  no longer add recipients. Check existing notifications for `|`, `{%` or
  variables other than `form_data` in `recipients` before upgrading.

### Features

- New `validate_notification_recipients(configured_form, renderer,
  notifications, *, email_field_types=...)` for the form type's `validate`
  function. It returns an `Error` for every `{{ form_data.<name> }}` in a
  notification's `recipients` whose field is missing or is not an email field
  (by default only `SimpleFieldBase.Type.EMAIL`; pass `email_field_types` to
  allow custom email fields). Previously such a notification passed the admin
  save and only failed at send time. Projects must add the call to their
  `validate` function (see README).

### Bugfixes

- `validate_recipients` now validates the fixed addresses in `recipients`
  even when the value also contains a template variable. Previously a value
  like `staff@exmaple, {{ form_data.email }}` passed the save and every
  notification failed at send time.
- `send_form_notifications` now skips rendered recipients that are not valid
  email addresses and sends the notification to the remaining ones, logging
  the skipped count at `ERROR`. Previously one invalid address, e.g. a
  submitter's typo, stopped the notification for all recipients. A
  notification without any valid recipient still fails as before.

## 0.3.5

### Features

- New optional XLSX export for form submissions. Install
  `feincms3-formbuilder[xlsx]` and use `make_export_action(renderer)` to add an
  admin action, or call `build_submissions_xlsx(queryset, renderer=renderer)`
  directly.

### Bugfixes

- `get_formatted_data` now sorts fields by region order first, then by
  `ordering` within each region. Previously fields were sorted by `ordering`
  alone, which produced wrong column order for multi-step forms.

## 0.3.4

### Features

- New `FORMBUILDER_CLIENT_IP_RESOLVER` setting. Points at a dotted-path
  callable used by `create_submission` to determine the client IP.
  Defaults to `REMOTE_ADDR`; deployments behind a proxy can supply a
  resolver that reads a forwarded header. A bad path is validated at
  startup and raises `ImproperlyConfigured`.

## 0.3.2

### Bugfixes

- Fixed a typo in the German translation.

## 0.3.1

### Bugfixes

- Added missing `back_label` and `next_label` fields to the `FormStepInline`
  admin so the fields introduced in 0.3.0 are actually editable in the Django
  admin.

## 0.3.0

### Features

- New `back_label` and `next_label` optional fields on `AbstractFormStep` to
  override the Back/Next/Submit button labels on a per-step basis. When blank,
  the template falls back to the translated default labels.
- Added German (de) and French (fr) translations.

## 0.2.0

### Features

- New `feincms3_formbuilder.notifications` module providing optional
  confirmation/staff emails after form submission. The package ships the
  abstract model and helper; projects own the concrete model, admin
  integration, and editor widget.
  - `AbstractFormNotification` abstract base with `recipients`, `subject`,
    and `body` fields.
  - `validate_recipients` validator (accepts either a comma-separated
    list of literal emails or any value containing a `{{ … }}`
    Django template variable).
  - `send_form_notifications(notifications, *, context, fail_silently=True,
    send_one=None)` helper. Renders each notification's `recipients`,
    `subject`, and `body` against the supplied context, generates a
    plain-text alternative via `html2text`, and sends an
    `EmailMultiAlternatives`. Per-notification failures are isolated and
    logged via the `feincms3_formbuilder.notifications` logger at `ERROR`
    by default; pass `fail_silently=False` to re-raise. Pass a custom
    `send_one=` to extend behaviour (e.g. honour project-added
    `reply_to`/`bcc` fields).
- `subject` and `recipients` render with autoescape **off** (plain text);
  `body` renders with autoescape **on** (HTML), so user-supplied form
  values interpolated into the HTML body are HTML-escaped while editor
  markup passes through unchanged.
- New `FORMBUILDER_FROM_EMAIL` setting (optional). When set and non-empty
  it is used as the From address for every notification, falling back to
  `settings.DEFAULT_FROM_EMAIL`.

### Dependencies

- New runtime dependency: `html2text` (used to generate the plain-text
  alternative from the rendered HTML body).

## 0.1.0

### Breaking changes

- `form_view_router` removed. Consumers replace it with a small project-side
  dispatch (see README's "Views and URLs" section).
- `multistep_form_view` now treats step regions as those whose key starts with
  `STEP_REGION_PREFIX` (`"step_"`). Previously every region except `"success"`
  was walked. The only step-region producer is `AbstractFormStep.region_key`,
  which already emits `step_<identifier>`, so well-behaved consumers see no
  behaviour change. Consumers with non-`step_*` step regions either rename
  them or pass a custom `get_step_regions` callable.

### Features

- `multistep_form_view` accepts `get_step_regions=<callable>` for non-standard
  step layouts.
- `STEP_REGION_PREFIX` exposed at `feincms3_formbuilder.models` as the single
  source of truth for the prefix; used by `AbstractFormStep.region_key`,
  `StepSlugField`, and the walker's default selector.

## 0.0.1

Initial release.
