from django.contrib import admin

from feincms3_formbuilder.admin import BaseFormSubmissionAdmin, make_export_action
from testapp.models import ConfiguredForm, FormSubmission
from testapp.renderer import renderer


admin.site.register(ConfiguredForm)


@admin.register(FormSubmission)
class FormSubmissionAdmin(BaseFormSubmissionAdmin):
    actions = [make_export_action(renderer)]
    search_fields = ["data", "configured_form__name"]
