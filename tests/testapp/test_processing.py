from django.apps import apps
from django.contrib.contenttypes.models import ContentType
from django.core import signing
from django.core.exceptions import ImproperlyConfigured
from django.test import RequestFactory, TestCase, override_settings

from feincms3_formbuilder.processing import (
    create_submission,
    render_success_region,
    resolve_ref,
)
from testapp.models import ConfiguredForm, FormSubmission


def _first_forwarded_for(request):
    header = request.META.get("HTTP_X_FORWARDED_FOR", "")
    return header.split(",")[0].strip() or request.META.get("REMOTE_ADDR")


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

    def test_uses_configured_resolver(self):
        # A site-supplied resolver replaces the REMOTE_ADDR default. This is
        # the escape hatch for deployments behind a proxy that need to trust
        # a forwarded header — trust policy lives in the site, not the lib.
        request = self.factory.post("/")
        request.META["REMOTE_ADDR"] = "10.0.0.1"
        request.META["HTTP_X_FORWARDED_FOR"] = "203.0.113.5, 10.0.0.1"
        with override_settings(
            FORMBUILDER_CLIENT_IP_RESOLVER="testapp.test_processing._first_forwarded_for"
        ):
            submission = create_submission(
                request, self.form, {"name": "Alice"},
                submission_model=FormSubmission,
            )
        self.assertEqual(submission.ip_address, "203.0.113.5")

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


class AppReadyValidationTest(TestCase):
    def setUp(self):
        self.app_config = apps.get_app_config("feincms3_formbuilder")

    def test_bad_resolver_path_raises_at_startup(self):
        # A misconfigured dotted path must fail loud at deploy time rather
        # than 500 on the first submission — that's the whole point of the
        # startup check.
        with override_settings(
            FORMBUILDER_CLIENT_IP_RESOLVER="does.not.exist.at_all"
        ):
            with self.assertRaises(ImproperlyConfigured):
                self.app_config.ready()

    def test_valid_resolver_path_passes(self):
        with override_settings(
            FORMBUILDER_CLIENT_IP_RESOLVER="testapp.test_processing._first_forwarded_for"
        ):
            self.app_config.ready()

    def test_unset_resolver_passes(self):
        self.app_config.ready()


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
