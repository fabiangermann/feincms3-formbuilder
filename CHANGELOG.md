# Changelog

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
