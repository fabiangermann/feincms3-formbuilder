from django.http import QueryDict
from django.test import SimpleTestCase, TestCase

from feincms3_formbuilder.admin import simple_field_inlines
from feincms3_formbuilder.conditionals import (
    controlling_value,
    get_condition,
    is_active,
)
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


class GetConditionTest(SimpleTestCase):
    def test_no_controlling_field_means_unconditional(self):
        self.assertIsNone(get_condition(SimpleField(show_when_values="phone")))

    def test_plugin_without_the_mixin_is_unconditional(self):
        """Projects may register plugins that never heard of conditions."""

        class Plain:
            name = "plain"

        self.assertIsNone(get_condition(Plain()))

    def test_condition_is_the_name_and_the_parsed_keys(self):
        plugin = SimpleField(
            show_when_field="contact_pref", show_when_values="Phone\nsms"
        )
        self.assertEqual(get_condition(plugin), ("contact_pref", ["phone", "sms"]))


class ControllingValueTest(SimpleTestCase):
    def test_missing_key_reads_as_unanswered(self):
        self.assertEqual(controlling_value("contact_pref", {}), "")

    def test_none_reads_as_unanswered(self):
        self.assertEqual(controlling_value("contact_pref", {"contact_pref": None}), "")

    def test_querydict_yields_the_submitted_value(self):
        data = QueryDict("contact_pref=phone")
        self.assertEqual(controlling_value("contact_pref", data), "phone")

    def test_non_string_session_value_is_coerced(self):
        """Session data comes back through JSON and is not always a string."""
        self.assertEqual(controlling_value("count", {"count": 3}), "3")


class IsActiveTest(SimpleTestCase):
    condition = ("contact_pref", ["phone", "sms"])

    def test_unconditional_field_is_always_active(self):
        self.assertTrue(is_active(None, {}))

    def test_matching_answer_activates(self):
        self.assertTrue(is_active(self.condition, {"contact_pref": "phone"}))

    def test_other_answer_deactivates(self):
        self.assertFalse(is_active(self.condition, {"contact_pref": "email"}))

    def test_unanswered_controlling_field_deactivates(self):
        """This is also the cross-step case: a step not yet reached has no answer."""
        self.assertFalse(is_active(self.condition, {}))

    def test_condition_without_values_never_matches(self):
        self.assertFalse(is_active(("contact_pref", []), {"contact_pref": "phone"}))
