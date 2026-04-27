import json

from django.test import RequestFactory, TestCase
from django.urls import reverse

from feincms3_formbuilder.views import _ref_initial

from testapp.models import (
    ConfiguredForm,
    Email,
    FormStep,
    FormSubmission,
    RichText,
    Text,
)


class SimpleFormViewTest(TestCase):
    def setUp(self):
        self.form = ConfiguredForm.objects.create(
            name="Contact",
            slug="contact",
            form_type="simple",
        )
        Text.objects.create(
            parent=self.form,
            region="form",
            ordering=10,
            name="name",
            label="Name",
            is_required=True,
        )
        RichText.objects.create(
            parent=self.form,
            region="success",
            ordering=10,
            text="<p>Thanks!</p>",
        )
        self.url = reverse("forms:form", kwargs={"slug": "contact"})

    def test_get_renders_form(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Name")

    def test_post_valid_creates_submission(self):
        response = self.client.post(self.url, {"name": "Alice"})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Thanks!")
        self.assertEqual(FormSubmission.objects.count(), 1)
        submission = FormSubmission.objects.first()
        self.assertEqual(submission.data["name"], "Alice")

    def test_post_invalid_shows_errors(self):
        response = self.client.post(self.url, {"name": ""})
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Thanks!")


class MultistepFormViewTest(TestCase):
    def setUp(self):
        self.form = ConfiguredForm.objects.create(
            name="Registration",
            slug="registration",
            form_type="multistep",
        )
        self.step1 = FormStep.objects.create(
            configured_form=self.form,
            title="Personal",
            identifier="personal",
            ordering=10,
        )
        self.step2 = FormStep.objects.create(
            configured_form=self.form,
            title="Contact",
            identifier="contact",
            ordering=20,
        )
        Text.objects.create(
            parent=self.form,
            region=self.step1.region_key,
            ordering=10,
            name="first_name",
            label="First Name",
            is_required=True,
        )
        Email.objects.create(
            parent=self.form,
            region=self.step2.region_key,
            ordering=10,
            name="email",
            label="Email",
            is_required=True,
        )
        RichText.objects.create(
            parent=self.form,
            region="success",
            ordering=10,
            text="<p>Done!</p>",
        )
        self.url = reverse("forms:form", kwargs={"slug": "registration"})

    def _post_step(self, data, action="next"):
        data["_action"] = action
        return self.client.post(self.url, data)

    def test_get_renders_first_step(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "First Name")
        self.assertNotContains(response, 'name="email"')

    def test_next_advances_to_step2(self):
        response = self._post_step({"first_name": "John"})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Email")

    def test_next_with_invalid_data_stays(self):
        response = self._post_step({"first_name": ""})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "First Name")

    def test_back_navigates_without_validation(self):
        self._post_step({"first_name": "John"})
        response = self._post_step({}, action="back")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "John")

    def test_submit_creates_submission(self):
        self._post_step({"first_name": "John"})
        response = self._post_step({"email": "john@example.com"}, action="submit")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Done!")
        self.assertEqual(FormSubmission.objects.count(), 1)
        submission = FormSubmission.objects.first()
        self.assertEqual(submission.data["first_name"], "John")
        self.assertEqual(submission.data["email"], "john@example.com")

    def test_submit_clears_session(self):
        self._post_step({"first_name": "John"})
        self._post_step({"email": "john@example.com"}, action="submit")
        session_key = f"multistep_form_{self.form.pk}"
        self.assertNotIn(session_key, self.client.session)

    def test_data_persists_across_steps(self):
        self._post_step({"first_name": "John"})
        session_key = f"multistep_form_{self.form.pk}"
        session_data = json.loads(self.client.session[session_key])
        self.assertEqual(session_data["data"]["first_name"], "John")

    def test_no_steps_renders_gracefully(self):
        form = ConfiguredForm.objects.create(
            name="Empty", slug="empty", form_type="multistep"
        )
        url = reverse("forms:form", kwargs={"slug": "empty"})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)


class FormViewRouterTest(TestCase):
    def test_routes_simple(self):
        form = ConfiguredForm.objects.create(
            name="Simple", slug="simple", form_type="simple"
        )
        Text.objects.create(
            parent=form, region="form", ordering=10,
            name="field", label="Field", is_required=True,
        )
        RichText.objects.create(
            parent=form, region="success", ordering=10, text="<p>OK</p>",
        )
        url = reverse("forms:form", kwargs={"slug": "simple"})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Field")

    def test_routes_multistep(self):
        form = ConfiguredForm.objects.create(
            name="Multi", slug="multi", form_type="multistep"
        )
        step = FormStep.objects.create(
            configured_form=form, title="Step", identifier="s", ordering=10,
        )
        Text.objects.create(
            parent=form, region=step.region_key, ordering=10,
            name="field", label="Field", is_required=True,
        )
        RichText.objects.create(
            parent=form, region="success", ordering=10, text="<p>OK</p>",
        )
        url = reverse("forms:form", kwargs={"slug": "multi"})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Field")


class RefInitialTest(TestCase):
    def setUp(self):
        self.factory = RequestFactory()

    def test_no_ref_returns_empty(self):
        request = self.factory.get("/")
        self.assertEqual(_ref_initial(request), {})

    def test_empty_ref_returns_empty(self):
        request = self.factory.get("/?ref=")
        self.assertEqual(_ref_initial(request), {})

    def test_ref_returned_under_underscore_key(self):
        request = self.factory.get("/?ref=signed-token")
        self.assertEqual(_ref_initial(request), {"_ref": "signed-token"})

    def test_view_with_ref_query_does_not_break(self):
        """Default form_class has no _ref field; the view must still render."""
        form = ConfiguredForm.objects.create(
            name="WithRef", slug="with-ref", form_type="simple"
        )
        Text.objects.create(
            parent=form, region="form", ordering=10,
            name="field", label="Field", is_required=True,
        )
        RichText.objects.create(
            parent=form, region="success", ordering=10, text="<p>OK</p>",
        )
        url = reverse("forms:form", kwargs={"slug": "with-ref"})
        response = self.client.get(url + "?ref=any-token")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Field")
