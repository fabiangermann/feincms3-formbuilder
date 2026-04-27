from django.test import TestCase

from feincms3_formbuilder.admin import FormStepInline, simple_field_inlines

from testapp.models import FormStep, SimpleField


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
