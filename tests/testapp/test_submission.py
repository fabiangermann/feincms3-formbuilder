from django.contrib.contenttypes.models import ContentType
from django.test import TestCase

from testapp.models import ConfiguredForm, FormSubmission, SimpleField, Text


class FormSubmissionTest(TestCase):
    def setUp(self):
        self.form = ConfiguredForm.objects.create(
            name="Test Form",
            form_type="simple",
        )

    def test_create_submission(self):
        submission = FormSubmission.objects.create(
            configured_form=self.form,
            data={"name": "Alice"},
            ip_address="127.0.0.1",
            user_agent="TestAgent/1.0",
        )
        self.assertEqual(submission.configured_form, self.form)
        self.assertEqual(submission.data["name"], "Alice")
        self.assertIsNotNone(submission.submitted_at)

    def test_str(self):
        submission = FormSubmission.objects.create(
            configured_form=self.form,
            data={},
        )
        self.assertIn("Test Form", str(submission))

    def test_ordering(self):
        s1 = FormSubmission.objects.create(configured_form=self.form, data={})
        s2 = FormSubmission.objects.create(configured_form=self.form, data={})
        submissions = list(FormSubmission.objects.all())
        self.assertEqual(submissions[0], s2)
        self.assertEqual(submissions[1], s1)

    def test_for_related_object(self):
        ct = ContentType.objects.get_for_model(self.form)
        FormSubmission.objects.create(
            configured_form=self.form,
            data={},
            related_content_type=ct,
            related_object_id=str(self.form.pk),
        )
        FormSubmission.objects.create(
            configured_form=self.form,
            data={},
        )
        self.assertEqual(
            FormSubmission.objects.for_related_object(self.form).count(), 1
        )

    def test_get_formatted_data(self):
        Text.objects.create(
            parent=self.form,
            region="form",
            ordering=10,
            name="name",
            label="Name",
            is_required=True,
        )
        submission = FormSubmission.objects.create(
            configured_form=self.form,
            data={"name": "Alice"},
        )
        formatted = submission.get_formatted_data()
        self.assertIn("Name", formatted)
        self.assertIn("Alice", formatted)
