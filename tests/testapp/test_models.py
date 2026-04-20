from django.core.exceptions import ValidationError
from django.test import TestCase

from feincms3_formbuilder.models import StepSlugField
from testapp.models import ConfiguredForm, FormStep


class StepSlugFieldTest(TestCase):
    def test_auto_generates_identifier_when_blank(self):
        field = StepSlugField(max_length=50)
        value = field.to_python("")
        self.assertEqual(len(value), 10)

    def test_preserves_explicit_value(self):
        field = StepSlugField(max_length=50)
        value = field.to_python("my_step")
        self.assertEqual(value, "my_step")

    def test_rejects_invalid_identifier(self):
        field = StepSlugField(max_length=50)
        with self.assertRaises(ValidationError):
            field.to_python("123-invalid!")

    def test_deconstructs_as_charfield(self):
        field = StepSlugField(max_length=50)
        _name, path, _args, _kwargs = field.deconstruct()
        self.assertEqual(path, "django.db.models.CharField")

    def test_formfield_not_required(self):
        field = StepSlugField(max_length=50)
        form_field = field.formfield()
        self.assertFalse(form_field.required)


class FormStepTest(TestCase):
    def setUp(self):
        self.form = ConfiguredForm.objects.create(
            name="Test Form",
            form_type="simple",
        )

    def test_region_key(self):
        step = FormStep.objects.create(
            configured_form=self.form,
            title="Personal Info",
            identifier="personal",
            ordering=10,
        )
        self.assertEqual(step.region_key, "step_personal")

    def test_auto_generates_identifier(self):
        step = FormStep(
            configured_form=self.form,
            title="Auto Step",
            ordering=10,
        )
        step.full_clean()
        step.save()
        self.assertTrue(step.identifier)
        self.assertTrue(step.region_key.startswith("step_"))

    def test_str(self):
        step = FormStep.objects.create(
            configured_form=self.form,
            title="My Step",
            identifier="my_step",
            ordering=10,
        )
        self.assertEqual(str(step), "My Step")


class AbstractConfiguredFormTest(TestCase):
    def test_simple_form_type_has_correct_regions(self):
        form = ConfiguredForm.objects.create(
            name="Simple",
            form_type="simple",
        )
        region_keys = [r.key for r in form.regions]
        self.assertEqual(region_keys, ["form", "success"])

    def test_multistep_form_type_generates_regions_from_steps(self):
        form = ConfiguredForm.objects.create(
            name="Multi",
            form_type="multistep",
        )
        FormStep.objects.create(
            configured_form=form,
            title="Step One",
            identifier="one",
            ordering=10,
        )
        FormStep.objects.create(
            configured_form=form,
            title="Step Two",
            identifier="two",
            ordering=20,
        )
        region_keys = [r.key for r in form.regions]
        self.assertEqual(region_keys, ["step_one", "step_two", "success"])

    def test_multistep_no_steps_returns_only_success(self):
        form = ConfiguredForm.objects.create(
            name="Empty Multi",
            form_type="multistep",
        )
        region_keys = [r.key for r in form.regions]
        self.assertEqual(region_keys, ["success"])

    def test_str(self):
        form = ConfiguredForm.objects.create(name="My Form", form_type="simple")
        self.assertEqual(str(form), "My Form")
