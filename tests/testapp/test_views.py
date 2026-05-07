import json

from content_editor.contents import contents_for_item
from django import forms
from django.contrib.sessions.backends.db import SessionStore
from django.test import RequestFactory, TestCase
from django.urls import reverse

from feincms3_formbuilder.views import (
    _default_get_step_regions,
    _ref_initial,
    compute_step_statuses,
    multistep_form_view,
)
from testapp.models import (
    ConfiguredForm,
    Email,
    FormStep,
    FormSubmission,
    RichText,
    Text,
)
from testapp.renderer import renderer


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

    def test_step_clamped_when_steps_removed(self):
        """Self-healing: session step gets clamped when steps are deleted between requests."""
        self._post_step({"first_name": "John"})

        session_key = f"multistep_form_{self.form.pk}"
        self.assertEqual(json.loads(self.client.session[session_key])["step"], 1)

        self.step2.delete()

        response = self.client.get(self.url)
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


class SingleStepFormViewTest(TestCase):
    """Multistep form with exactly one step: the only step is both first and last."""

    def setUp(self):
        self.form = ConfiguredForm.objects.create(
            name="Single", slug="single", form_type="multistep",
        )
        self.step = FormStep.objects.create(
            configured_form=self.form, title="Only",
            identifier="only", ordering=10,
        )
        Text.objects.create(
            parent=self.form, region=self.step.region_key, ordering=10,
            name="name", label="Name", is_required=True,
        )
        RichText.objects.create(
            parent=self.form, region="success", ordering=10, text="<p>Done!</p>",
        )
        self.url = reverse("forms:form", kwargs={"slug": "single"})

    def test_get_renders_only_step(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Name")

    def test_submit_completes_immediately(self):
        response = self.client.post(self.url, {"name": "Test", "_action": "submit"})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Done!")
        self.assertEqual(FormSubmission.objects.count(), 1)


class ComputeStepStatusesTest(TestCase):
    """Direct coverage of the three status branches in compute_step_statuses."""

    def setUp(self):
        self.form = ConfiguredForm.objects.create(
            name="StatusForm", slug="status-form", form_type="multistep",
        )
        self.step1 = FormStep.objects.create(
            configured_form=self.form, title="Personal",
            identifier="personal", ordering=10,
        )
        self.step2 = FormStep.objects.create(
            configured_form=self.form, title="Contact",
            identifier="contact", ordering=20,
        )
        Text.objects.create(
            parent=self.form, region=self.step1.region_key, ordering=10,
            name="first_name", label="First Name", is_required=True,
        )
        Email.objects.create(
            parent=self.form, region=self.step2.region_key, ordering=10,
            name="email", label="Email", is_required=True,
        )
        RichText.objects.create(
            parent=self.form, region="success", ordering=10, text="<p>OK</p>",
        )
        self.contents = contents_for_item(self.form, plugins=renderer.plugins())
        self.step_regions = [r for r in self.form.regions if r.key != "success"]

    def test_all_empty_when_no_data(self):
        statuses = compute_step_statuses(
            self.contents, self.step_regions, {}, 0, form_class=forms.Form,
        )
        for s in statuses:
            self.assertEqual(s["status"], "empty")

    def test_valid_for_step_with_complete_data(self):
        statuses = compute_step_statuses(
            self.contents, self.step_regions,
            {"first_name": "John"}, 0, form_class=forms.Form,
        )
        self.assertEqual(statuses[0]["status"], "valid")
        self.assertEqual(statuses[1]["status"], "empty")

    def test_invalid_for_step_with_bad_data(self):
        statuses = compute_step_statuses(
            self.contents, self.step_regions,
            {"email": "not-an-email"}, 1, form_class=forms.Form,
        )
        self.assertEqual(statuses[1]["status"], "invalid")


class DefaultGetStepRegionsTest(TestCase):
    def _form_with_regions(self, region_keys):
        form = ConfiguredForm(name="X", form_type="multistep")
        # Stub `regions` so we can test the selector in isolation,
        # without coupling to FormStep/FormType wiring.
        form.regions = [type("R", (), {"key": k, "title": k})() for k in region_keys]
        return form

    def test_picks_step_prefixed_regions(self):
        form = self._form_with_regions(["step_one", "step_two", "success"])
        result = _default_get_step_regions(form)
        self.assertEqual([r.key for r in result], ["step_one", "step_two"])

    def test_ignores_arbitrary_non_step_regions(self):
        form = self._form_with_regions(["step_a", "result_low", "result_high"])
        result = _default_get_step_regions(form)
        self.assertEqual([r.key for r in result], ["step_a"])

    def test_preserves_order(self):
        form = self._form_with_regions(["step_b", "step_a", "step_c"])
        result = _default_get_step_regions(form)
        self.assertEqual([r.key for r in result], ["step_b", "step_a", "step_c"])


class MultistepFormViewCustomStepRegionsTest(TestCase):
    def setUp(self):
        self.form = ConfiguredForm.objects.create(
            name="Custom",
            slug="custom-walker",
            form_type="multistep",
        )
        self.step1 = FormStep.objects.create(
            configured_form=self.form,
            title="One",
            identifier="one",
            ordering=10,
        )
        self.step2 = FormStep.objects.create(
            configured_form=self.form,
            title="Two",
            identifier="two",
            ordering=20,
        )
        Text.objects.create(
            parent=self.form,
            region=self.step1.region_key,
            ordering=10,
            name="a",
            label="A",
            is_required=True,
        )
        Text.objects.create(
            parent=self.form,
            region=self.step2.region_key,
            ordering=10,
            name="b",
            label="B",
            is_required=True,
        )

    def test_custom_callable_controls_walked_regions(self):
        def only_second(cf):
            return [r for r in cf.regions if r.key == "step_two"]

        request = RequestFactory().get(
            f"/forms/{self.form.slug}/", SERVER_NAME="testserver",
        )
        request.session = SessionStore()

        response = multistep_form_view(
            request, self.form,
            renderer=renderer,
            get_step_regions=only_second,
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'name="b"')
        self.assertNotContains(response, 'name="a"')
