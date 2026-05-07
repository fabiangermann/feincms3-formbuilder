from content_editor.models import Region, create_plugin_base
from django.db import models
from feincms3_forms import models as forms_models

from feincms3_formbuilder.models import (
    AbstractConfiguredForm,
    AbstractFormStep,
    AbstractFormSubmission,
)
from feincms3_formbuilder.notifications import AbstractFormNotification


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
            validate="testapp.validation.validate_configured_form",
            process="testapp.processing.process_simple_form",
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
            validate="testapp.validation.validate_configured_form",
            process="testapp.processing.process_multistep_form",
        ),
    ]

    class Meta(AbstractConfiguredForm.Meta):
        pass


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


class FormSubmission(AbstractFormSubmission):
    configured_form = models.ForeignKey(
        ConfiguredForm,
        on_delete=models.CASCADE,
        related_name="submissions",
    )

    def get_formatted_data(self):
        return super().get_formatted_data(field_model=SimpleField)


class FormNotification(AbstractFormNotification):
    configured_form = models.ForeignKey(
        ConfiguredForm,
        on_delete=models.CASCADE,
        related_name="notifications",
    )


class RichText(ConfiguredFormPlugin):
    text = models.TextField(blank=True)

    class Meta:
        verbose_name = "rich text"
        verbose_name_plural = "rich texts"
