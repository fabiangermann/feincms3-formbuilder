import logging

from django.core import mail
from django.core.exceptions import ValidationError
from django.template.exceptions import TemplateSyntaxError
from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse
from feincms3_forms import validation

from feincms3_formbuilder.notifications import (
    AbstractFormNotification,
    _parse_recipients,
    _send_one,
    send_form_notifications,
    validate_notification_recipients,
    validate_recipients,
)
from testapp.models import (
    ConfiguredForm,
    Email,
    FormNotification,
    RichText,
    SimpleField,
    Text,
)
from testapp.renderer import renderer


class ValidateRecipientsTest(SimpleTestCase):
    def test_empty_string_rejected(self):
        with self.assertRaises(ValidationError) as ctx:
            validate_recipients("")
        self.assertEqual(ctx.exception.code, "empty")

    def test_whitespace_only_rejected(self):
        with self.assertRaises(ValidationError) as ctx:
            validate_recipients("   ")
        self.assertEqual(ctx.exception.code, "empty")

    def test_none_rejected(self):
        with self.assertRaises(ValidationError) as ctx:
            validate_recipients(None)
        self.assertEqual(ctx.exception.code, "empty")

    def test_single_literal_email_accepted(self):
        validate_recipients("info@example.com")

    def test_multiple_literal_emails_accepted(self):
        validate_recipients("info@example.com, sales@example.com")

    def test_trailing_empty_token_rejected(self):
        with self.assertRaises(ValidationError) as ctx:
            validate_recipients("info@example.com, ")
        self.assertEqual(ctx.exception.code, "empty_token")

    def test_invalid_literal_email_rejected(self):
        with self.assertRaises(ValidationError) as ctx:
            validate_recipients("not-an-email")
        self.assertEqual(ctx.exception.code, "invalid")

    def test_invalid_among_valid_rejected(self):
        with self.assertRaises(ValidationError) as ctx:
            validate_recipients("info@example.com, broken")
        self.assertEqual(ctx.exception.code, "invalid")

    def test_single_variable_accepted(self):
        validate_recipients("{{ form_data.email }}")

    def test_variable_with_filter_rejected(self):
        with self.assertRaises(ValidationError) as ctx:
            validate_recipients("{{ form_data.email|lower }}")
        self.assertEqual(ctx.exception.code, "unsupported_template")

    def test_multiple_variables_accepted(self):
        validate_recipients("{{ form_data.a }}, {{ form_data.b }}")

    def test_variable_mixed_with_literal_accepted(self):
        validate_recipients("info@example.com, {{ form_data.email }}")

    def test_variable_outside_form_data_rejected(self):
        """Only form_data variables can be checked against the form's fields."""
        with self.assertRaises(ValidationError) as ctx:
            validate_recipients("{{ submission.data.contact }}")
        self.assertEqual(ctx.exception.code, "unsupported_template")

    def test_tag_rejected(self):
        with self.assertRaises(ValidationError) as ctx:
            validate_recipients(
                "{% if form_data.copy %}{{ form_data.email }}, {% endif %}"
                "staff@example.com"
            )
        self.assertEqual(ctx.exception.code, "unsupported_template")

    def test_template_syntax_accepted_by_email_validator_rejected(self):
        """EmailValidator accepts braces, but here they are a mistake."""
        for value in ["{{form_data.user}}@example.com", "user}}@example.com"]:
            with self.subTest(value=value):
                with self.assertRaises(ValidationError) as ctx:
                    validate_recipients(value)
                self.assertEqual(ctx.exception.code, "unsupported_template")

    def test_invalid_literal_mixed_with_variable_rejected(self):
        """A typo in a fixed address would otherwise break every send."""
        with self.assertRaises(ValidationError) as ctx:
            validate_recipients("staff@exmaple, {{ form_data.email }}")
        self.assertEqual(ctx.exception.code, "invalid")

    def test_empty_token_mixed_with_variable_rejected(self):
        with self.assertRaises(ValidationError) as ctx:
            validate_recipients("{{ form_data.email }}, ")
        self.assertEqual(ctx.exception.code, "empty_token")


class AbstractFormNotificationTest(SimpleTestCase):
    def test_is_abstract(self):
        self.assertTrue(AbstractFormNotification._meta.abstract)

    def test_has_recipients_field(self):
        field = AbstractFormNotification._meta.get_field("recipients")
        self.assertEqual(field.max_length, 500)

    def test_has_subject_field(self):
        field = AbstractFormNotification._meta.get_field("subject")
        self.assertEqual(field.max_length, 500)

    def test_has_body_field(self):
        AbstractFormNotification._meta.get_field("body")

    def test_str_returns_subject(self):
        instance = FormNotification(subject="Hello")
        self.assertEqual(str(instance), "Hello")


class AbstractFormNotificationFullCleanTest(SimpleTestCase):
    def test_full_clean_attaches_blank_error_to_recipients(self):
        instance = FormNotification(
            recipients="", subject="s", body="b",
        )
        with self.assertRaises(ValidationError) as ctx:
            instance.full_clean(exclude=["configured_form"])
        self.assertIn("recipients", ctx.exception.error_dict)
        self.assertEqual(
            ctx.exception.error_dict["recipients"][0].code, "blank",
        )

    def test_full_clean_attaches_invalid_email_error_to_recipients(self):
        instance = FormNotification(
            recipients="not-an-email", subject="s", body="b",
        )
        with self.assertRaises(ValidationError) as ctx:
            instance.full_clean(exclude=["configured_form"])
        self.assertIn("recipients", ctx.exception.error_dict)
        self.assertEqual(
            ctx.exception.error_dict["recipients"][0].code, "invalid",
        )

    def test_full_clean_accepts_valid_recipients(self):
        instance = FormNotification(
            recipients="info@example.com", subject="s", body="b",
        )
        instance.full_clean(exclude=["configured_form"])


class ParseRecipientsTest(SimpleTestCase):
    def test_single_email(self):
        self.assertEqual(
            _parse_recipients("info@example.com", {}), (["info@example.com"], 0),
        )

    def test_multiple_emails(self):
        self.assertEqual(
            _parse_recipients("info@example.com, sales@example.com", {}),
            (["info@example.com", "sales@example.com"], 0),
        )

    def test_strips_whitespace(self):
        self.assertEqual(
            _parse_recipients("  info@example.com  ,  sales@example.com  ", {}),
            (["info@example.com", "sales@example.com"], 0),
        )

    def test_skips_empty_tokens(self):
        self.assertEqual(
            _parse_recipients("info@example.com, ,sales@example.com", {}),
            (["info@example.com", "sales@example.com"], 0),
        )

    def test_empty_input_raises(self):
        with self.assertRaises(ValidationError) as ctx:
            _parse_recipients("", {})
        self.assertEqual(ctx.exception.code, "no_recipients")

    def test_only_whitespace_raises(self):
        with self.assertRaises(ValidationError) as ctx:
            _parse_recipients("   ,  ", {})
        self.assertEqual(ctx.exception.code, "no_recipients")

    def test_skips_invalid_emails(self):
        self.assertEqual(
            _parse_recipients("info@example.com, not-an-email", {}),
            (["info@example.com"], 1),
        )

    def test_only_invalid_emails_raises(self):
        with self.assertRaises(ValidationError) as ctx:
            _parse_recipients("not-an-email", {})
        self.assertEqual(ctx.exception.code, "no_recipients")

    def test_resolves_form_data_variable(self):
        self.assertEqual(
            _parse_recipients(
                "{{ form_data.email }}", {"email": "alice@example.com"},
            ),
            (["alice@example.com"], 0),
        )

    def test_empty_form_data_value_skipped(self):
        """An optional email field left blank is not an error."""
        self.assertEqual(
            _parse_recipients(
                "staff@example.com, {{ form_data.email }}", {"email": ""},
            ),
            (["staff@example.com"], 0),
        )

    def test_comma_in_submitted_value_not_split(self):
        """Submitted values must not be able to add recipients."""
        self.assertEqual(
            _parse_recipients(
                "staff@example.com, {{ form_data.email }}",
                {"email": "a@example.com, b@example.com"},
            ),
            (["staff@example.com"], 1),
        )

    def test_unsupported_template_counted_as_invalid(self):
        """Values saved before tags and filters were rejected still send."""
        self.assertEqual(
            _parse_recipients(
                "staff@example.com, {{ form_data.email|lower }}",
                {"email": "alice@example.com"},
            ),
            (["staff@example.com"], 1),
        )


class FormNotificationModelTest(TestCase):
    def test_fk_related_name_is_notifications(self):
        cf = ConfiguredForm.objects.create(name="Test", form_type="simple")
        n = FormNotification.objects.create(
            configured_form=cf,
            recipients="info@example.com",
            subject="Hello",
            body="<p>Hi</p>",
        )
        self.assertEqual(cf.notifications.count(), 1)
        self.assertEqual(cf.notifications.get(), n)


class SendOneTest(TestCase):
    def setUp(self):
        self.cf = ConfiguredForm.objects.create(name="Test", form_type="simple")

    def test_sends_email_with_rendered_fields(self):
        n = FormNotification.objects.create(
            configured_form=self.cf,
            recipients="info@example.com",
            subject="Hello {{ form_data.name }}",
            body="<p>Thanks {{ form_data.name }}.</p>",
        )
        _send_one(n, {"form_data": {"name": "Alice"}})
        self.assertEqual(len(mail.outbox), 1)
        message = mail.outbox[0]
        self.assertEqual(message.subject, "Hello Alice")
        self.assertEqual(message.to, ["info@example.com"])
        self.assertIn("Thanks Alice", message.body)
        self.assertEqual(len(message.alternatives), 1)
        html_content, mimetype = message.alternatives[0]
        self.assertEqual(mimetype, "text/html")
        self.assertIn("<p>Thanks Alice.</p>", html_content)

    def test_renders_recipients_from_context(self):
        n = FormNotification.objects.create(
            configured_form=self.cf,
            recipients="{{ form_data.email }}",
            subject="Hi",
            body="<p>Hi</p>",
        )
        _send_one(n, {"form_data": {"email": "alice@example.com"}})
        self.assertEqual(mail.outbox[-1].to, ["alice@example.com"])

    def test_html_body_autoescape_on(self):
        n = FormNotification.objects.create(
            configured_form=self.cf,
            recipients="info@example.com",
            subject="s",
            body="<p>{{ form_data.note }}</p>",
        )
        _send_one(n, {"form_data": {"note": "<script>x</script>"}})
        html_content, _ = mail.outbox[-1].alternatives[0]
        self.assertIn("&lt;script&gt;x&lt;/script&gt;", html_content)
        self.assertNotIn("<script>x</script>", html_content)

    def test_subject_autoescape_off(self):
        n = FormNotification.objects.create(
            configured_form=self.cf,
            recipients="info@example.com",
            subject="Order #{{ form_data.id }} & status",
            body="<p>x</p>",
        )
        _send_one(n, {"form_data": {"id": "42"}})
        self.assertEqual(mail.outbox[-1].subject, "Order #42 & status")

    def test_recipients_autoescape_off(self):
        n = FormNotification.objects.create(
            configured_form=self.cf,
            recipients="{{ form_data.email }}",
            subject="s",
            body="<p>x</p>",
        )
        _send_one(n, {"form_data": {"email": "a+b&c@example.com"}})
        self.assertEqual(mail.outbox[-1].to, ["a+b&c@example.com"])

    def test_uses_default_from_email(self):
        n = FormNotification.objects.create(
            configured_form=self.cf,
            recipients="info@example.com",
            subject="s",
            body="<p>x</p>",
        )
        _send_one(n, {})
        self.assertEqual(mail.outbox[-1].from_email, "noreply@example.com")

    @override_settings(FORMBUILDER_FROM_EMAIL="forms@example.com")
    def test_formbuilder_from_email_takes_precedence(self):
        n = FormNotification.objects.create(
            configured_form=self.cf,
            recipients="info@example.com",
            subject="s",
            body="<p>x</p>",
        )
        _send_one(n, {})
        self.assertEqual(mail.outbox[-1].from_email, "forms@example.com")

    @override_settings(FORMBUILDER_FROM_EMAIL="")
    def test_empty_formbuilder_from_email_falls_back(self):
        n = FormNotification.objects.create(
            configured_form=self.cf,
            recipients="info@example.com",
            subject="s",
            body="<p>x</p>",
        )
        _send_one(n, {})
        self.assertEqual(mail.outbox[-1].from_email, "noreply@example.com")

    def test_invalid_rendered_recipient_raises(self):
        n = FormNotification.objects.create(
            configured_form=self.cf,
            recipients="{{ form_data.email }}",
            subject="s",
            body="<p>x</p>",
        )
        with self.assertRaises(ValidationError):
            _send_one(n, {"form_data": {"email": "not-an-email"}})

    def test_invalid_rendered_recipient_skipped_and_logged(self):
        """One bad submitter address must not stop the staff copy."""
        n = FormNotification.objects.create(
            configured_form=self.cf,
            recipients="staff@example.com, {{ form_data.email }}",
            subject="s",
            body="<p>x</p>",
        )
        with self.assertLogs(
            "feincms3_formbuilder.notifications", level=logging.ERROR,
        ) as captured:
            _send_one(n, {"form_data": {"email": "not-an-email"}})
        self.assertEqual(mail.outbox[-1].to, ["staff@example.com"])
        self.assertIn(repr(n), captured.output[0])


class SendFormNotificationsTest(TestCase):
    def setUp(self):
        self.cf = ConfiguredForm.objects.create(name="Test", form_type="simple")

    def _make(self, **kwargs):
        kwargs.setdefault("configured_form", self.cf)
        kwargs.setdefault("recipients", "info@example.com")
        kwargs.setdefault("subject", "s")
        kwargs.setdefault("body", "<p>x</p>")
        return FormNotification.objects.create(**kwargs)

    def test_sends_all_notifications(self):
        a = self._make(recipients="a@example.com")
        b = self._make(recipients="b@example.com")
        send_form_notifications([a, b], context={})
        recipients = sorted(m.to[0] for m in mail.outbox)
        self.assertEqual(recipients, ["a@example.com", "b@example.com"])

    def test_fail_silently_default_swallows_errors(self):
        bad = self._make(subject="{% bogus %}")
        good = self._make(recipients="ok@example.com")
        with self.assertLogs(
            "feincms3_formbuilder.notifications", level=logging.ERROR,
        ) as captured:
            send_form_notifications([bad, good], context={})
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ["ok@example.com"])
        self.assertTrue(any("Failed to send" in r for r in captured.output))

    def test_fail_silently_false_reraises(self):
        bad = self._make(subject="{% bogus %}")
        with self.assertRaises(TemplateSyntaxError):
            send_form_notifications([bad], context={}, fail_silently=False)

    def test_custom_send_one_is_used(self):
        calls = []

        def custom_send_one(notification, context):
            calls.append((notification.pk, dict(context)))

        n = self._make()
        send_form_notifications(
            [n], context={"key": "value"}, send_one=custom_send_one,
        )
        self.assertEqual(calls, [(n.pk, {"key": "value"})])
        self.assertEqual(len(mail.outbox), 0)

    def test_invalid_rendered_recipient_logged_under_default(self):
        n = self._make(recipients="{{ form_data.email }}")
        with self.assertLogs(
            "feincms3_formbuilder.notifications", level=logging.ERROR,
        ):
            send_form_notifications(
                [n], context={"form_data": {"email": "not-an-email"}},
            )
        self.assertEqual(len(mail.outbox), 0)

    def test_empty_iterable_is_noop(self):
        send_form_notifications([], context={})
        self.assertEqual(len(mail.outbox), 0)


class EndToEndNotificationsTest(TestCase):
    def setUp(self):
        self.cf = ConfiguredForm.objects.create(
            name="Contact", slug="contact-end-to-end", form_type="simple",
        )
        Email.objects.create(
            parent=self.cf, region="form", ordering=10,
            name="email", label="Email", is_required=True,
        )
        Text.objects.create(
            parent=self.cf, region="form", ordering=20,
            name="name", label="Name", is_required=True,
        )
        RichText.objects.create(
            parent=self.cf, region="success", ordering=10,
            text="<p>Thanks!</p>",
        )

    def test_simple_form_post_sends_both_notifications(self):
        FormNotification.objects.create(
            configured_form=self.cf,
            recipients="staff@example.com",
            subject="New submission from {{ form_data.name }}",
            body="<p>{{ form_data.name }} ({{ form_data.email }}) submitted.</p>",
        )
        FormNotification.objects.create(
            configured_form=self.cf,
            recipients="{{ form_data.email }}",
            subject="Thanks {{ form_data.name }}",
            body="<p>Thanks for getting in touch.</p>",
        )

        url = reverse("forms:form", kwargs={"slug": "contact-end-to-end"})
        response = self.client.post(url, {
            "name": "Alice",
            "email": "alice@example.com",
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Thanks!")
        self.assertEqual(len(mail.outbox), 2)
        sent_to = sorted(m.to[0] for m in mail.outbox)
        self.assertEqual(sent_to, ["alice@example.com", "staff@example.com"])
        staff_msg = next(m for m in mail.outbox if m.to == ["staff@example.com"])
        self.assertEqual(staff_msg.subject, "New submission from Alice")
        self.assertIn(
            "Alice (alice@example.com) submitted.",
            staff_msg.alternatives[0][0],
        )
        user_msg = next(m for m in mail.outbox if m.to == ["alice@example.com"])
        self.assertEqual(user_msg.subject, "Thanks Alice")
        self.assertIn(
            "Thanks for getting in touch.", user_msg.alternatives[0][0],
        )



class ValidateNotificationRecipientsTest(TestCase):
    """Recipient templates must point at email fields of the form.

    Otherwise the notification fails only once a submission arrives with a
    value that isn't an email address, and the submitter never learns about it.
    """

    def setUp(self):
        self.cf = ConfiguredForm.objects.create(name="Test", form_type="simple")
        Email.objects.create(
            parent=self.cf, region="form", ordering=10,
            name="email", label="Email",
        )
        Text.objects.create(
            parent=self.cf, region="form", ordering=20,
            name="name", label="Name",
        )

    def _validate(self, recipients, **kwargs):
        FormNotification.objects.create(
            configured_form=self.cf,
            recipients=recipients,
            subject="Hi",
            body="<p>Hi</p>",
        )
        return validate_notification_recipients(
            self.cf, renderer, self.cf.notifications.all(), **kwargs,
        )

    def test_email_field_accepted(self):
        self.assertEqual(
            self._validate("staff@example.com, {{ form_data.email }}"), [],
        )

    def test_text_field_is_error(self):
        errors = self._validate("staff@example.com, {{ form_data.name }}")
        self.assertEqual(len(errors), 1)
        self.assertIsInstance(errors[0], validation.Error)
        self.assertIn("'name'", errors[0].message)

    def test_configured_field_types_accepted(self):
        """Projects with custom email field types list them explicitly."""
        errors = self._validate(
            "{{ form_data.name }}",
            email_field_types=[SimpleField.Type.EMAIL, SimpleField.Type.TEXT],
        )
        self.assertEqual(errors, [])

    def test_missing_field_is_error(self):
        errors = self._validate("{{ form_data.e_mail }}")
        self.assertEqual(len(errors), 1)
        self.assertIsInstance(errors[0], validation.Error)
        self.assertIn("'e_mail'", errors[0].message)
