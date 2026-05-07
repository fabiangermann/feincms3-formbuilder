from django.contrib.contenttypes.models import ContentType
from django.core import signing
from django.test import RequestFactory, TestCase

from feincms3_formbuilder.processing import (
    create_submission,
    render_success_region,
    resolve_ref,
)
from testapp.models import ConfiguredForm, FormSubmission


class ResolveRefTest(TestCase):
    def setUp(self):
        self.form = ConfiguredForm.objects.create(
            name="Test", form_type="simple"
        )
        self.ct = ContentType.objects.get_for_model(self.form)
        self.valid_ref = signing.dumps({
            "ct": f"{self.ct.app_label}.{self.ct.model}",
            "oid": str(self.form.pk),
        })

    def test_valid_ref(self):
        data = {"_ref": self.valid_ref, "name": "Alice"}
        result = resolve_ref(data)
        self.assertEqual(result["related_content_type"], self.ct)
        self.assertEqual(result["related_object_id"], str(self.form.pk))
        self.assertNotIn("_ref", data)

    def test_no_ref(self):
        data = {"name": "Alice"}
        result = resolve_ref(data)
        self.assertEqual(result, {})

    def test_empty_ref(self):
        data = {"_ref": "", "name": "Alice"}
        result = resolve_ref(data)
        self.assertEqual(result, {})

    def test_invalid_signature(self):
        data = {"_ref": "bad-token", "name": "Alice"}
        result = resolve_ref(data)
        self.assertEqual(result, {})
        self.assertNotIn("_ref", data)

    def test_nonexistent_object(self):
        ref = signing.dumps({
            "ct": f"{self.ct.app_label}.{self.ct.model}",
            "oid": "99999",
        })
        data = {"_ref": ref}
        result = resolve_ref(data)
        self.assertEqual(result, {})


class CreateSubmissionTest(TestCase):
    def setUp(self):
        self.form = ConfiguredForm.objects.create(
            name="Test", form_type="simple"
        )
        self.factory = RequestFactory()

    def test_creates_submission(self):
        request = self.factory.post("/")
        request.META["REMOTE_ADDR"] = "10.0.0.1"
        request.META["HTTP_USER_AGENT"] = "TestAgent"
        data = {"name": "Alice", "email": "alice@example.com"}
        submission = create_submission(
            request, self.form, data, submission_model=FormSubmission
        )
        self.assertEqual(submission.configured_form, self.form)
        self.assertEqual(submission.data["name"], "Alice")
        self.assertEqual(submission.ip_address, "10.0.0.1")
        self.assertEqual(submission.user_agent, "TestAgent")

    def test_creates_submission_with_ref(self):
        ct = ContentType.objects.get_for_model(self.form)
        ref = signing.dumps({
            "ct": f"{ct.app_label}.{ct.model}",
            "oid": str(self.form.pk),
        })
        request = self.factory.post("/")
        data = {"name": "Alice", "_ref": ref}
        submission = create_submission(
            request, self.form, data, submission_model=FormSubmission
        )
        self.assertEqual(submission.related_content_type, ct)
        self.assertEqual(submission.related_object_id, str(self.form.pk))
        self.assertNotIn("_ref", submission.data)


class RenderSuccessRegionTest(TestCase):
    def setUp(self):
        self.form = ConfiguredForm.objects.create(
            name="Test", form_type="simple"
        )

    def test_renders_success_content(self):
        from testapp.models import RichText

        RichText.objects.create(
            parent=self.form,
            region="success",
            ordering=10,
            text="<p>Thank you!</p>",
        )
        from testapp.renderer import renderer

        request = RequestFactory().get("/")
        response = render_success_region(request, self.form, renderer=renderer)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Thank you!", response.content)
