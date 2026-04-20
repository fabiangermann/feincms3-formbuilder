from django.test import TestCase

from feincms3_formbuilder.admin import FormStepInline, simple_field_inlines

from testapp.models import SimpleField


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
