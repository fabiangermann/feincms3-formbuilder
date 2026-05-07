from django.contrib.admin.sites import AdminSite
from django.contrib.contenttypes.models import ContentType
from django.test import TestCase

from feincms3_formbuilder.admin import (
    BaseFormSubmissionAdmin,
    FormStepInline,
    simple_field_inlines,
)
from testapp.models import (
    ConfiguredForm,
    FormStep,
    FormSubmission,
    SimpleField,
    Text,
)


class SimpleFieldInlinesTest(TestCase):
    def test_returns_eleven_inlines(self):
        inlines = simple_field_inlines(SimpleField)
        self.assertEqual(len(inlines), 11)

    def test_each_inline_is_a_class(self):
        inlines = simple_field_inlines(SimpleField)
        for inline in inlines:
            self.assertTrue(isinstance(inline, type))


class FormStepInlineTest(TestCase):
    def test_has_expected_fields(self):
        self.assertIn("title", FormStepInline.fields)
        self.assertIn("identifier", FormStepInline.fields)
        self.assertIn("ordering", FormStepInline.fields)

    def test_for_model_returns_subclass_bound_to_model(self):
        inline_cls = FormStepInline.for_model(FormStep)

        self.assertTrue(issubclass(inline_cls, FormStepInline))
        self.assertIs(inline_cls.model, FormStep)
        self.assertEqual(inline_cls.fields, FormStepInline.fields)
        self.assertNotEqual(inline_cls, FormStepInline)


class BaseFormSubmissionAdminTest(TestCase):
    def setUp(self):
        self.form = ConfiguredForm.objects.create(
            name="Form", slug="form", form_type="simple",
        )
        Text.objects.create(
            parent=self.form, region="form", ordering=10,
            name="name", label="Name", is_required=True,
        )
        self.admin = BaseFormSubmissionAdmin(FormSubmission, AdminSite())

    def test_formatted_data_display_delegates_to_instance(self):
        submission = FormSubmission.objects.create(
            configured_form=self.form,
            data={"name": "Alice"},
        )
        self.assertEqual(
            self.admin.formatted_data_display(submission),
            submission.get_formatted_data(),
        )

    def test_related_object_link_returns_dash_when_unset(self):
        submission = FormSubmission.objects.create(
            configured_form=self.form, data={},
        )
        self.assertEqual(self.admin.related_object_link(submission), "-")

    def test_related_object_link_returns_anchor_when_set(self):
        ct = ContentType.objects.get_for_model(self.form)
        submission = FormSubmission.objects.create(
            configured_form=self.form,
            data={},
            related_content_type=ct,
            related_object_id=str(self.form.pk),
        )
        link = self.admin.related_object_link(submission)
        self.assertIn("<a href=", link)
        self.assertIn(str(self.form.pk), link)

    def test_has_add_permission_is_false(self):
        self.assertFalse(self.admin.has_add_permission(request=None))
