from django.test import SimpleTestCase, TestCase

from feincms3_formbuilder.admin import simple_field_inlines
from feincms3_formbuilder.models import ConditionalFieldMixin
from testapp.models import SimpleField


class ShowWhenValuesListTest(SimpleTestCase):
    """The parsing must accept whatever an editor plausibly copies in.

    Editors see ``choices`` right next to ``show_when_values``, so they type
    the label, the key, or a whole ``key | Label`` line. All three have to
    reduce to the key the browser actually submits.
    """

    def test_label_key_and_pipe_lines_all_reduce_to_the_key(self):
        field = SimpleField(show_when_values="Phone\nsms\nemail | E-Mail")
        self.assertEqual(field.show_when_values_list, ["phone", "sms", "email"])

    def test_blank_lines_are_ignored(self):
        field = SimpleField(show_when_values="phone\n\n   \nsms\n")
        self.assertEqual(field.show_when_values_list, ["phone", "sms"])

    def test_no_values_is_an_empty_list(self):
        self.assertEqual(SimpleField().show_when_values_list, [])


class ConditionalAdminFieldsTest(TestCase):
    """Without this the two fields exist but no editor can reach them."""

    def test_inlines_expose_the_condition_fields(self):
        self.assertTrue(issubclass(SimpleField, ConditionalFieldMixin))
        for inline in simple_field_inlines(SimpleField):
            self.assertIn("show_when_field", inline.advanced_fields)
            self.assertIn("show_when_values", inline.advanced_fields)

    def test_existing_advanced_fields_are_kept(self):
        inline = simple_field_inlines(SimpleField)[0]
        self.assertIn("help_text", inline.advanced_fields)
