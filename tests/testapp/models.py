from content_editor.models import create_plugin_base
from django.db import models
from feincms3_forms import models as forms_models

from feincms3_formbuilder.models import (
    AbstractConfiguredForm,
    AbstractFormStep,
    AbstractFormSubmission,
)


class ConfiguredForm(AbstractConfiguredForm):
    class Meta:
        verbose_name = "configured form"
        verbose_name_plural = "configured forms"


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
