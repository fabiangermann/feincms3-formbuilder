from django.core.exceptions import ValidationError
from django.test import SimpleTestCase, TestCase

from feincms3_formbuilder.notifications import AbstractFormNotification, _parse_recipients, validate_recipients
from testapp.models import ConfiguredForm, FormNotification


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

    def test_variable_with_filter_accepted(self):
        validate_recipients("{{ form_data.email|lower }}")

    def test_multiple_variables_accepted(self):
        validate_recipients("{{ form_data.a }}, {{ form_data.b }}")

    def test_variable_mixed_with_literal_accepted(self):
        validate_recipients("info@example.com, {{ form_data.email }}")

    def test_arbitrary_variable_path_accepted(self):
        validate_recipients("{{ submission.data.contact }}")


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
        self.assertEqual(_parse_recipients("info@example.com"), ["info@example.com"])

    def test_multiple_emails(self):
        self.assertEqual(
            _parse_recipients("info@example.com, sales@example.com"),
            ["info@example.com", "sales@example.com"],
        )

    def test_strips_whitespace(self):
        self.assertEqual(
            _parse_recipients("  info@example.com  ,  sales@example.com  "),
            ["info@example.com", "sales@example.com"],
        )

    def test_skips_empty_tokens(self):
        self.assertEqual(
            _parse_recipients("info@example.com, ,sales@example.com"),
            ["info@example.com", "sales@example.com"],
        )

    def test_empty_input_raises(self):
        with self.assertRaises(ValidationError) as ctx:
            _parse_recipients("")
        self.assertEqual(ctx.exception.code, "no_recipients")

    def test_only_whitespace_raises(self):
        with self.assertRaises(ValidationError) as ctx:
            _parse_recipients("   ,  ")
        self.assertEqual(ctx.exception.code, "no_recipients")

    def test_invalid_email_raises(self):
        with self.assertRaises(ValidationError) as ctx:
            _parse_recipients("not-an-email")
        self.assertEqual(ctx.exception.code, "invalid")


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
