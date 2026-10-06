from django.http import QueryDict
from django.template import Context
from django.test import SimpleTestCase, TestCase
from django.urls import reverse
from feincms3_forms.renderer import create_form

from feincms3_formbuilder.admin import simple_field_inlines
from feincms3_formbuilder.conditionals import (
    _controlling_value,
    _get_condition,
    _is_active,
    condition_context,
    create_form_with_conditionals,
)
from feincms3_formbuilder.models import ConditionalFieldMixin
from feincms3_formbuilder.renderer import render_form_field
from testapp.models import (
    ConfiguredForm,
    FormSubmission,
    Radio,
    RichText,
    SimpleField,
    Text,
)


class ShowWhenValuesListTest(SimpleTestCase):
    """The keys are compared verbatim with the submitted answer, so stray
    whitespace or a blank line in the textarea must not produce a key that
    never matches or, worse, an empty key that matches an unanswered field."""

    def test_lines_are_stripped(self):
        field = SimpleField(show_when_values="  phone \nsms\t")
        self.assertEqual(field.show_when_values_list, ["phone", "sms"])

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
        self.assertIsNone(_get_condition(SimpleField(show_when_values="phone")))

    def test_plugin_without_the_mixin_is_unconditional(self):
        """Projects may register plugins that never heard of conditions."""

        class Plain:
            name = "plain"

        self.assertIsNone(_get_condition(Plain()))

    def test_unrelated_show_when_field_attribute_is_ignored(self):
        """Only the mixin opts a plugin in; a project plugin that happens to
        have an attribute of that name, but no ``show_when_values_list``,
        must neither turn conditional nor crash the form."""

        class Lookalike:
            name = "lookalike"
            show_when_field = "contact_pref"

        self.assertIsNone(_get_condition(Lookalike()))

    def test_condition_is_the_name_and_the_keys(self):
        plugin = SimpleField(
            show_when_field="contact_pref", show_when_values="phone\nsms"
        )
        self.assertEqual(_get_condition(plugin), ("contact_pref", ["phone", "sms"]))


class ControllingValueTest(SimpleTestCase):
    def test_missing_key_reads_as_unanswered(self):
        self.assertEqual(_controlling_value("contact_pref", {}), "")

    def test_none_reads_as_unanswered(self):
        self.assertEqual(_controlling_value("contact_pref", {"contact_pref": None}), "")

    def test_querydict_yields_the_submitted_value(self):
        data = QueryDict("contact_pref=phone")
        self.assertEqual(_controlling_value("contact_pref", data), "phone")

    def test_non_string_session_value_is_coerced(self):
        """Session data comes back through JSON and is not always a string."""
        self.assertEqual(_controlling_value("count", {"count": 3}), "3")


class IsActiveTest(SimpleTestCase):
    condition = ("contact_pref", ["phone", "sms"])

    def test_unconditional_field_is_always_active(self):
        self.assertTrue(_is_active(None, {}))

    def test_matching_answer_activates(self):
        self.assertTrue(_is_active(self.condition, {"contact_pref": "phone"}))

    def test_other_answer_deactivates(self):
        self.assertFalse(_is_active(self.condition, {"contact_pref": "email"}))

    def test_unanswered_controlling_field_deactivates(self):
        """This is also the cross-step case: a step not yet reached has no answer."""
        self.assertFalse(_is_active(self.condition, {}))

    def test_condition_without_values_never_matches(self):
        self.assertFalse(_is_active(("contact_pref", []), {"contact_pref": "phone"}))


class ConditionalFormTestCase(TestCase):
    """Shared fixture: a radio control and a required text field depending on it.

    Holds no tests of its own, so subclasses reusing the fixture don't re-run
    them under their own names.
    """

    def setUp(self):
        self.configured_form = ConfiguredForm.objects.create(
            name="Contact", slug="contact-build", form_type="simple",
        )
        self.control = Radio.objects.create(
            parent=self.configured_form, region="form", ordering=10,
            name="contact_pref", label="Preferred contact",
            is_required=True, choices="Phone\nEmail",
        )
        self.conditional = Text.objects.create(
            parent=self.configured_form, region="form", ordering=20,
            name="phone", label="Phone number", is_required=True,
            show_when_field="contact_pref", show_when_values="phone",
        )
        self.plugins = [self.control, self.conditional]

    def _form(self, data=None, **kwargs):
        return create_form_with_conditionals(
            self.plugins,
            form_kwargs={"data": data} if data is not None else {},
            **kwargs,
        )


class ConditionalFormBuildingTest(ConditionalFormTestCase):
    """The server is the authority: what it builds decides what is accepted."""

    def test_matching_answer_keeps_the_field_required(self):
        form = self._form({"contact_pref": "phone"})
        self.assertTrue(form.fields["phone"].required)
        self.assertNotIn("phone", form._f3fb_conditionals.inactive)
        self.assertFalse(form.is_valid())
        self.assertIn("phone", form.errors)

    def test_other_answer_clears_required_and_drops_the_value(self):
        form = self._form({"contact_pref": "email", "phone": "123"})
        self.assertFalse(form.fields["phone"].required)
        self.assertIn("phone", form._f3fb_conditionals.inactive)
        self.assertTrue(form.is_valid())
        self.assertNotIn("phone", form.cleaned_data)

    def test_inactive_field_cannot_block_submission(self):
        """Other validation still runs; its errors must not survive either.

        A client that submits garbage for a field the user was never shown
        would otherwise produce an error on an invisible field.
        """
        self.conditional.max_length = 3
        self.conditional.save()
        form = self._form({"contact_pref": "email", "phone": "far too long"})
        self.assertTrue(form.is_valid())
        self.assertNotIn("phone", form.cleaned_data)

    def test_inactive_inputs_are_disabled_and_remember_required(self):
        """``data-required`` is what lets the script restore native validation."""
        form = self._form({"contact_pref": "email"})
        attrs = form.fields["phone"].widget.attrs
        self.assertTrue(attrs["disabled"])
        self.assertTrue(attrs["data-required"])

    def test_active_field_carries_no_condition_attributes(self):
        form = self._form({"contact_pref": "phone"})
        self.assertNotIn("disabled", form.fields["phone"].widget.attrs)
        self.assertNotIn("data-required", form.fields["phone"].widget.attrs)

    def test_unbound_form_falls_back_to_initial(self):
        """A controlling select with a default value is answered before the
        user touches it, so its dependent field must render visible at once."""
        self.control.default_value = "Phone"
        self.control.save()
        form = self._form()
        self.assertEqual(form._f3fb_conditionals.inactive, set())

    def test_explicit_available_data_wins_over_the_form(self):
        """The multistep step POST needs this: the controlling answer lives in
        the session, not in the current step's POST."""
        form = self._form({}, available_data={"contact_pref": "phone"})
        self.assertTrue(form.fields["phone"].required)

    def test_unsupported_controlling_field_deactivates_and_logs(self):
        """Pointing at a text field silently shows nothing; the log is the only
        runtime symptom, so it has to carry the field names.

        The controlling field is a second plugin rather than a retyped first
        one: ``SimpleFieldBase.save()`` resets ``type`` from the proxy class,
        so assigning a different type and saving would not stick.
        """
        nickname = Text.objects.create(
            parent=self.configured_form, region="form", ordering=5,
            name="nickname", label="Nickname",
        )
        self.conditional.show_when_field = "nickname"
        with self.assertLogs("feincms3_formbuilder.conditionals", "WARNING") as logs:
            form = create_form_with_conditionals(
                [nickname, self.control, self.conditional],
                form_kwargs={"data": {"nickname": "anything"}},
            )
        self.assertIn("phone", form._f3fb_conditionals.inactive)
        self.assertIn("nickname", logs.output[0])

    def test_condition_is_exposed_for_the_renderer(self):
        form = self._form({"contact_pref": "email"})
        condition = form._f3fb_conditionals.conditions[self.conditional]
        self.assertEqual(condition["field"], "contact_pref")
        self.assertEqual(condition["values"], '["phone"]')
        self.assertFalse(condition["active"])


class ConditionContextTest(ConditionalFormTestCase):
    def test_unconditional_plugin_has_no_context(self):
        form = self._form({"contact_pref": "phone"})
        self.assertEqual(condition_context(form, self.control), {})

    def test_form_built_without_the_wrapper_has_no_context(self):
        """Projects calling create_form directly must not crash the renderer."""
        form = create_form(self.plugins, form_kwargs={})
        self.assertEqual(condition_context(form, self.conditional), {})


class RenderFormFieldTest(ConditionalFormTestCase):
    """The page must show what the server decided, not wait for JavaScript."""

    def _render(self, plugin, data):
        form = self._form(data)
        return render_form_field(plugin, Context({"form": form}))

    def test_inactive_field_renders_hidden_with_the_attributes(self):
        html = self._render(self.conditional, {"contact_pref": "email"})
        self.assertIn('data-show-when-field="contact_pref"', html)
        self.assertIn("data-show-when-values='[&quot;phone&quot;]'", html)
        self.assertRegex(html, r"<div[^>]*\shidden")
        self.assertRegex(html, r"<input[^>]*\sdisabled")

    def test_active_field_renders_visible(self):
        html = self._render(self.conditional, {"contact_pref": "phone"})
        self.assertIn('data-show-when-field="contact_pref"', html)
        self.assertIn("data-show-when-values='[&quot;phone&quot;]'", html)
        self.assertNotRegex(html, r"\shidden")
        self.assertNotRegex(html, r"<input[^>]*\sdisabled")

    def test_unconditional_field_emits_no_attributes(self):
        html = self._render(self.control, {"contact_pref": "phone"})
        self.assertNotIn("data-show-when", html)
        self.assertNotRegex(html, r"\shidden")


class ConditionalSimpleFormTest(TestCase):
    """Without the view wiring the conditions exist but never take effect."""

    def setUp(self):
        self.configured_form = ConfiguredForm.objects.create(
            name="Contact",
            slug="contact-simple",
            form_type="simple",
        )
        Radio.objects.create(
            parent=self.configured_form,
            region="form",
            ordering=10,
            name="contact_pref",
            label="Preferred contact",
            is_required=True,
            choices="Phone\nEmail",
        )
        Text.objects.create(
            parent=self.configured_form,
            region="form",
            ordering=20,
            name="phone",
            label="Phone number",
            is_required=True,
            show_when_field="contact_pref",
            show_when_values="phone",
        )
        RichText.objects.create(
            parent=self.configured_form,
            region="success",
            ordering=10,
            text="<p>Thanks!</p>",
        )
        self.url = reverse("forms:form", kwargs={"slug": "contact-simple"})

    def test_first_get_hides_the_conditional_field(self):
        """Targets the wrapper: csrf_token inputs make a bare "hidden" match always."""
        response = self.client.get(self.url)
        self.assertRegex(
            response.content.decode(),
            r'<div[^>]*data-show-when-field="contact_pref"[^>]*\shidden',
        )

    def test_matching_answer_without_the_value_is_rejected(self):
        """The no-JavaScript round-trip: the server asks for the field it
        would have revealed, instead of accepting a silently missing answer."""
        response = self.client.post(self.url, {"contact_pref": "phone"})
        self.assertNotContains(response, "Thanks!")
        self.assertEqual(FormSubmission.objects.count(), 0)
        self.assertContains(response, "This field is required.")

    def test_matching_answer_stores_the_value(self):
        response = self.client.post(
            self.url, {"contact_pref": "phone", "phone": "555-0100"}
        )
        self.assertContains(response, "Thanks!")
        self.assertEqual(FormSubmission.objects.get().data["phone"], "555-0100")

    def test_other_answer_submits_without_the_field(self):
        response = self.client.post(self.url, {"contact_pref": "email"})
        self.assertContains(response, "Thanks!")
        self.assertNotIn("phone", FormSubmission.objects.get().data)

    def test_value_for_an_inactive_field_is_never_stored(self):
        """A client that submits it anyway must not get it into the database."""
        response = self.client.post(
            self.url, {"contact_pref": "email", "phone": "555-0100"}
        )
        self.assertContains(response, "Thanks!")
        self.assertNotIn("phone", FormSubmission.objects.get().data)
