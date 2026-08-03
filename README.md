# feincms3-formbuilder

feincms3-formbuilder provides the abstract models, views, processing helpers,
renderer factory, admin utilities, and templates needed to build a form-builder
app on top of [feincms3-forms](https://github.com/feincms/feincms3-forms).  Its
relationship to feincms3-forms mirrors the relationship of
[feincms3](https://github.com/feincms/feincms3) to
[django-content-editor](https://github.com/feincms/django-content-editor): the
lower-level library defines the protocol; feincms3-formbuilder wires everything
together so that projects only need to write the thin, project-specific layer.

---

## Installation

```
pip install feincms3-formbuilder
```

Add the app to `INSTALLED_APPS`:

```python
INSTALLED_APPS = [
    ...
    "content_editor",
    "feincms3_forms",
    "feincms3_formbuilder",
    ...
]
```

---

## Models

Create four concrete models in your app.

### ConfiguredForm

Subclass `AbstractConfiguredForm`, add any project fields (e.g. a slug), and
override `FORMS` to point `validate` and `process` at your own functions:

```python
# myapp/models.py
from content_editor.models import Region, create_plugin_base
from django.db import models
from feincms3_forms import models as forms_models
from feincms3_formbuilder.models import (
    AbstractConfiguredForm,
    AbstractFormStep,
    AbstractFormSubmission,
)


class ConfiguredForm(AbstractConfiguredForm):
    slug = models.SlugField(unique=True, blank=True)

    FORMS = [
        forms_models.FormType(
            key="simple",
            label="simple form",
            regions=[
                Region(key="form", title="Form fields"),
                Region(key="success", title="Success message"),
            ],
            form_class="django.forms.Form",
            validate="myapp.validation.validate_configured_form",
            process="myapp.processing.process_simple_form",
        ),
        forms_models.FormType(
            key="multistep",
            label="multi-step form",
            regions=lambda configured_form: (
                (
                    [
                        Region(key=step.region_key, title=step.title)
                        for step in configured_form.steps.all()
                    ]
                    if configured_form.pk
                    else []
                )
                + [Region(key="success", title="Success message")]
            ),
            form_class="django.forms.Form",
            validate="myapp.validation.validate_configured_form",
            process="myapp.processing.process_multistep_form",
        ),
    ]
```

### FormStep

Subclass `AbstractFormStep` and add a FK to `ConfiguredForm`.  The
`AbstractFormStep` provides `title`, an auto-generated `identifier` (used as
the region key), and `ordering`:

```python
class FormStep(AbstractFormStep):
    configured_form = models.ForeignKey(
        ConfiguredForm,
        on_delete=models.CASCADE,
        related_name="steps",
    )

    class Meta(AbstractFormStep.Meta):
        unique_together = [
            ("configured_form", "ordering"),
            ("configured_form", "identifier"),
        ]
```

### FormSubmission

Subclass `AbstractFormSubmission`, add a FK to `ConfiguredForm`, and override
`get_formatted_data` to pass your field model:

```python
class FormSubmission(AbstractFormSubmission):
    configured_form = models.ForeignKey(
        ConfiguredForm,
        on_delete=models.CASCADE,
        related_name="submissions",
    )

    def get_formatted_data(self):
        return super().get_formatted_data(field_model=SimpleField)
```

`AbstractFormSubmission` stores `submitted_at`, `data` (JSON), `ip_address`,
`user_agent`, and optional `related_content_type` / `related_object_id`
generic FK fields (used for the submission-ref feature described below).

`AbstractConfiguredForm` and `AbstractFormStep` both ship with `created_at`
(`auto_now_add=True`) and `updated_at` (`auto_now=True`).  The default
`ordering` on `AbstractConfiguredForm` is `["-created_at"]`.

### SimpleField and proxy models

Create the plugin base, a `SimpleField` model, and proxy models for each
field type you want to support:

```python
ConfiguredFormPlugin = create_plugin_base(ConfiguredForm)


class SimpleField(forms_models.SimpleFieldBase, ConfiguredFormPlugin):
    class Meta:
        verbose_name = "form field"
        verbose_name_plural = "form fields"


Text = SimpleField.proxy(SimpleField.Type.TEXT)
Email = SimpleField.proxy(SimpleField.Type.EMAIL)
URL = SimpleField.proxy(SimpleField.Type.URL)
Date = SimpleField.proxy(SimpleField.Type.DATE)
Integer = SimpleField.proxy(SimpleField.Type.INTEGER)
Textarea = SimpleField.proxy(SimpleField.Type.TEXTAREA)
Checkbox = SimpleField.proxy(SimpleField.Type.CHECKBOX)
Select = SimpleField.proxy(SimpleField.Type.SELECT)
Radio = SimpleField.proxy(SimpleField.Type.RADIO)
SelectMultiple = SimpleField.proxy(SimpleField.Type.SELECT_MULTIPLE)
CheckboxSelectMultiple = SimpleField.proxy(SimpleField.Type.CHECKBOX_SELECT_MULTIPLE)
```

You can add further non-field plugins (e.g. a `RichText`) the same way any
django-content-editor plugin is added.

---

## Processing

A `process` function receives the request and validated data and must return
an `HttpResponse`.  Use the `create_submission` and `render_success_region`
helpers to keep the implementation minimal.

**Simple form** — receives a bound, valid `form`:

```python
# myapp/processing.py
from feincms3_formbuilder.processing import create_submission, render_success_region
from myapp.models import FormSubmission
from myapp.renderer import renderer


def process_simple_form(request, form, *, configured_form):
    data = dict(form.cleaned_data)
    create_submission(request, configured_form, data, submission_model=FormSubmission)
    return render_success_region(request, configured_form, renderer=renderer)
```

**Multi-step form** — receives `accumulated_data` collected across all steps:

```python
def process_multistep_form(request, configured_form, accumulated_data):
    data = dict(accumulated_data)
    create_submission(request, configured_form, data, submission_model=FormSubmission)
    return render_success_region(request, configured_form, renderer=renderer)
```

`create_submission` automatically extracts the `_ref` token (see
[Templatetags](#templatetags)) from `data`, verifies it, and stores the
resolved generic FK on the submission.

---

## Notifications

`feincms3-formbuilder` ships an optional notification module that lets a
project send confirmation/staff emails after a form submission. The
package provides the abstract model, validator, and helper; the project
owns the concrete model, admin integration, and editor widget.

### Concrete `FormNotification` model

```python
from feincms3_formbuilder.notifications import AbstractFormNotification


class FormNotification(AbstractFormNotification):
    configured_form = models.ForeignKey(
        ConfiguredForm,
        on_delete=models.CASCADE,
        related_name="notifications",
    )
```

`AbstractFormNotification` provides three fields:

| Field | Purpose |
|---|---|
| `recipients` | Comma-separated emails or a Django template variable that resolves to one (e.g. `{{ form_data.email }}`) |
| `subject` | Plain-text subject; supports template variables |
| `body` | HTML body; supports template variables; rendered with autoescape on |

The `recipients` field is validated at save time (via `validators=[validate_recipients]` on the field):

- Empty values are rejected.
- If the value contains any `{{ … }}` it is accepted as-is (the package
  cannot inspect what's in the project's context).
- Otherwise each comma-separated token must validate as an email.

### Sending notifications from `process()`

```python
# myapp/processing.py
from feincms3_formbuilder.processing import create_submission, render_success_region
from feincms3_formbuilder.notifications import send_form_notifications


def process_simple_form(request, form, *, configured_form):
    data = dict(form.cleaned_data)
    submission = create_submission(
        request, configured_form, data, submission_model=FormSubmission,
    )
    send_form_notifications(
        configured_form.notifications.all(),
        context={"form_data": data, "submission": submission},
    )
    return render_success_region(request, configured_form, renderer=renderer)
```

`context` is a plain dict; whatever keys you place there are available
to the editor as Django template variables in `recipients`, `subject`,
and `body`. The `form_data` key is the documented standard (used by the
notification body's help text); other keys are project-specific.

### Variables for editors

Documented out of the box:

- `{{ form_data.<field_name> }}` — any cleaned value from the form

Anything else (a submission link, a related-object link, a project-
specific identifier) is whatever the project decides to put in `context`.

### Failure handling

`send_form_notifications` defaults to `fail_silently=True`: per-notification
failures (template syntax errors, invalid rendered recipients, SMTP errors)
are logged via the `feincms3_formbuilder.notifications` logger at `ERROR`
and the remaining notifications continue to send. Pass
`fail_silently=False` to re-raise instead — useful in tests.

### `FORMBUILDER_FROM_EMAIL` setting

The From address used for every notification is, in order:

1. `settings.FORMBUILDER_FROM_EMAIL` if set and non-empty
2. `settings.DEFAULT_FROM_EMAIL`

### `FORMBUILDER_CLIENT_IP_RESOLVER` setting

`create_submission` stores the client IP on each submission. By default it
uses `REMOTE_ADDR` (the TCP peer address), which cannot be spoofed by
clients. Deployments behind a proxy — where `REMOTE_ADDR` is the proxy —
should set `FORMBUILDER_CLIENT_IP_RESOLVER` to a dotted path to a callable
`(request) -> str | None` that consults the appropriate forwarded header:

```python
# settings.py
FORMBUILDER_CLIENT_IP_RESOLVER = "myproject.utils.client_ip"

# myproject/utils.py
def client_ip(request):
    xff = request.META.get("HTTP_X_FORWARDED_FOR", "")
    return xff.split(",")[0].strip() or request.META.get("REMOTE_ADDR")
```

No forwarded header is honored by default because trusting one without a
proxy in front would let clients spoof their own IP. The resolver lives
in your project so the trust model (which header, how many hops) is
explicit.

### Admin integration

The package ships no admin classes for notifications. Wire your inline
in your project admin:

```python
class FormNotificationInline(admin.TabularInline):
    model = FormNotification
    extra = 0


@admin.register(ConfiguredForm)
class ConfiguredFormAdmin(admin.ModelAdmin):
    inlines = [
        FormStepInline.for_model(FormStep),
        FormNotificationInline,
        *simple_field_inlines(SimpleField),
    ]
```

For a rich-text editor on `body`, use `formfield_overrides` or a custom
`ModelForm`:

```python
from django_prose_editor.fields import ProseEditorFormField

class FormNotificationInlineForm(forms.ModelForm):
    body = ProseEditorFormField()
    class Meta:
        model = FormNotification
        fields = "__all__"

class FormNotificationInline(admin.TabularInline):
    model = FormNotification
    form = FormNotificationInlineForm
```

### Extending with extra fields

Projects that want `from_email` / `reply_to` / `bcc` / `cc` add fields
to their concrete subclass and pass a custom `send_one` to the helper:

```python
from feincms3_formbuilder.notifications import send_form_notifications

def my_send_one(notification, context):
    # Build EmailMultiAlternatives including notification.reply_to etc.
    ...

send_form_notifications(
    configured_form.notifications.all(),
    context={"form_data": data, "submission": submission},
    send_one=my_send_one,
)
```

---

## Validation

Implement a `validate` function that returns a list of error strings.  Use the
`validate_with_renderer` helper so that field-name uniqueness is checked across
all plugins registered with your renderer:

```python
# myapp/validation.py
from feincms3_formbuilder.models import validate_with_renderer
from myapp.renderer import renderer


def validate_configured_form(configured_form):
    return validate_with_renderer(configured_form, renderer)
```

---

## Renderer

Call `create_form_renderer()` with your field-producing plugin models as
positional arguments and any non-field plugins via `extra_plugins`:

```python
# myapp/renderer.py
from feincms3.renderer import template_renderer
from feincms3_formbuilder.renderer import create_form_renderer
from myapp.models import NewsletterField, RichText, SimpleField

renderer = create_form_renderer(
    SimpleField,
    NewsletterField,
    extra_plugins={
        RichText: template_renderer("myapp/richtext.html"),
    },
)
```

`create_form_renderer(*field_models, extra_plugins=None)` returns a
`RegionRenderer` where:

- Every model in `field_models` is wired to the built-in `render_form_field`
  handler, which renders each field using
  `feincms3_formbuilder/form_field.html`.  Pass any number of plugin models
  here — they all share that same wrapper template.
- Every model in `extra_plugins` is registered with the renderer callable you
  provide.  Use this for plugins that are not form fields (e.g. a `RichText`
  block) **or** for field plugins that need different outer markup than
  `form_field.html` — in that case write a custom renderer that calls
  `form.get_form_fields(plugin)` itself.

If you want every field to render through your own template, override
`feincms3_formbuilder/form_field.html` in your project's templates directory
rather than registering each model individually.

---

## Admin

Use `ConfiguredFormAdmin` together with the `simple_field_inlines()` helper and
`FormStepInline`:

```python
# myapp/admin.py
from django.contrib import admin
from feincms3_formbuilder.admin import FormStepInline, simple_field_inlines
from myapp.models import ConfiguredForm, FormStep, SimpleField


@admin.register(ConfiguredForm)
class ConfiguredFormAdmin(admin.ModelAdmin):
    inlines = [
        FormStepInline.for_model(FormStep),
        *simple_field_inlines(SimpleField),
    ]
```

`simple_field_inlines(model)` returns one `SimpleFieldInline` per field type,
each pre-configured with a Material Icons button and a `deny_regions({"success"})`
constraint so that field plugins cannot be placed in the success region.

`FormStepInline` is an `OrderableAdmin` `TabularInline`.  Bind it to your
concrete `FormStep` model with `FormStepInline.for_model(FormStep)`, or by
subclassing and setting `model` explicitly.

For the submission admin, subclass `BaseFormSubmissionAdmin`:

```python
from feincms3_formbuilder.admin import BaseFormSubmissionAdmin
from myapp.models import FormSubmission


@admin.register(FormSubmission)
class FormSubmissionAdmin(BaseFormSubmissionAdmin):
    pass  # add project-specific actions, list_filter etc. here
```

`BaseFormSubmissionAdmin` ships:

- `list_display`, `list_filter`, `date_hierarchy`, and a two-section `fieldsets`
  (main data + related object) covering every field on `AbstractFormSubmission`
  plus the consumer's required `configured_form` FK.
- `formatted_data_display` — calls `obj.get_formatted_data()`.
- `related_object_link` — resolves the generic FK (`related_content_type` /
  `related_object_id`) to an admin change-page link, or `-` when unset.
- `has_add_permission()` returning `False` (submissions are user-generated).

---

## Submission export (XLSX)

An optional Excel export of form submissions, exposed as an admin action.
Install the extra, which pulls in
[`xlsxdocument`](https://pypi.org/project/xlsxdocument/) (and `openpyxl`):

```
pip install feincms3-formbuilder[xlsx]
```

`make_export_action(renderer)` builds an admin action; add it to your
submission admin's `actions`:

```python
from feincms3_formbuilder.admin import BaseFormSubmissionAdmin, make_export_action
from myapp.models import FormSubmission
from myapp.renderer import renderer


@admin.register(FormSubmission)
class FormSubmissionAdmin(BaseFormSubmissionAdmin):
    actions = [make_export_action(renderer)]
```

The produced workbook:

- **One sheet per configured form**, named after the form.
- **Columns**: `ID`, `submitted at`, `IP address`, `user agent`, then one
  column per form field.

To build the document outside the admin (e.g. from a management command), call
the helper directly — it returns an `xlsxdocument.XLSXDocument`:

```python
from feincms3_formbuilder.reporting import build_submissions_xlsx

xlsx = build_submissions_xlsx(FormSubmission.objects.all(), renderer=renderer)
response = xlsx.to_response("form-submissions.xlsx")
```

`build_submissions_xlsx` raises `ImproperlyConfigured` if the `xlsx` extra is
not installed.

---

## Views and URLs

Write a thin wrapper that looks up the `ConfiguredForm` and dispatches to
`simple_form_view` or `multistep_form_view`:

```python
# myapp/views.py
from django.shortcuts import get_object_or_404
from feincms3_formbuilder.views import multistep_form_view, simple_form_view
from myapp.models import ConfiguredForm
from myapp.renderer import renderer


def form_view(request, slug):
    configured_form = get_object_or_404(ConfiguredForm, slug=slug)
    if configured_form.form_type == "multistep":
        return multistep_form_view(request, configured_form, renderer=renderer)
    return simple_form_view(request, configured_form, renderer=renderer)
```

```python
# myapp/urls.py
from django.urls import path
from myapp import views

app_name = "forms"

urlpatterns = [
    path("<slug:slug>/", views.form_view, name="form"),
]
```

The dispatch lives in your project because your project owns the `FORMS`
configuration that defines which form types exist. The `"multistep"` string
above must match the `key=` you set on the corresponding `FormType` in
`FORMS`.

`multistep_form_view` walks all regions whose key starts with
`STEP_REGION_PREFIX` (`"step_"`) — this matches `AbstractFormStep.region_key`.
Pass `get_step_regions=` (a callable `(configured_form) -> list[Region]`) to
override the selection, e.g. to mix step regions with project-specific
content regions.

---

## Templates

The package ships three minimal templates under
`feincms3_formbuilder/`:

| Template | Used by |
|---|---|
| `form.html` | `simple_form_view` — wraps the form in a `<form>` tag with a Submit button |
| `multistep_form.html` | `multistep_form_view` — adds step navigation, Back / Next / Submit buttons |
| `form_field.html` | `render_form_field` — renders label, widget, help text, and errors for each field |

Override any of them by creating a file at the same path inside your project's
template directories.  For example, to style the step navigation, copy
`feincms3_formbuilder/multistep_form.html` into your app's
`templates/feincms3_formbuilder/` directory and modify it as needed.

---

## Templatetags

Load `feincms3_formbuilder_tags` to access the `make_submission_ref` filter.
It signs a content-type / object-id pair so that a form submission can be
linked back to a related object (e.g. an event registration linked to an event):

```html
{% load feincms3_formbuilder_tags %}

<form method="post">
  {% csrf_token %}
  <input type="hidden" name="_ref" value="{{ event|make_submission_ref }}">
  ...
</form>
```

When `create_submission` processes the form data it pops `_ref`, verifies the
signature, and stores the resolved generic FK on the submission.  You can then
query submissions for a specific object:

```python
FormSubmission.objects.for_related_object(event)
```

The view layer also reads `?ref=` from the GET query string and pre-fills it
into the form's `initial` data under the key `_ref`.  This lets you link to a
form with `?ref={{ obj|make_submission_ref }}` and have the token survive
through the form submission, provided your form class declares a hidden
`_ref` field:

```python
from django import forms

class BaseForm(forms.Form):
    _ref = forms.CharField(required=False, widget=forms.HiddenInput)
```

If your form class has no `_ref` field the initial value is silently ignored.
