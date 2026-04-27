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

Call `create_form_renderer()` with your `SimpleField` model.  Pass additional
plugins via `extra_plugins`:

```python
# myapp/renderer.py
from feincms3.renderer import template_renderer
from feincms3_formbuilder.renderer import create_form_renderer
from myapp.models import RichText, SimpleField

renderer = create_form_renderer(
    SimpleField,
    extra_plugins={
        RichText: template_renderer("myapp/richtext.html"),
    },
)
```

`create_form_renderer` returns a `RegionRenderer` where every model in
`field_models` is wired to the built-in `render_form_field` handler, which
renders each field using `feincms3_formbuilder/form_field.html`.

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

`FormStepInline` is an `OrderableAdmin` `TabularInline` ready to use; supply
the concrete `FormStep` model via `for_model()` or by setting `model` on a
subclass.

---

## Views and URLs

Write a thin wrapper that looks up the `ConfiguredForm` and delegates to
`form_view_router`:

```python
# myapp/views.py
from django.shortcuts import get_object_or_404
from feincms3_formbuilder.views import form_view_router
from myapp.models import ConfiguredForm
from myapp.renderer import renderer


def form_view(request, slug):
    configured_form = get_object_or_404(ConfiguredForm, slug=slug)
    return form_view_router(request, configured_form, renderer=renderer)
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

`form_view_router` inspects `configured_form.form_type` and dispatches to
`simple_form_view` or `multistep_form_view`.  Both are importable directly
from `feincms3_formbuilder.views` if you need to call them without the router.

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
