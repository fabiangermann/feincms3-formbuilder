from django.contrib.contenttypes.models import ContentType
from django.core import signing
from django.test import TestCase

from feincms3_formbuilder.templatetags.feincms3_formbuilder_tags import (
    make_submission_ref,
)
from testapp.models import ConfiguredForm


class MakeSubmissionRefTest(TestCase):
    def test_generates_valid_signed_token(self):
        form = ConfiguredForm.objects.create(
            name="Test", form_type="simple"
        )
        ref = make_submission_ref(form)
        payload = signing.loads(ref)
        ct = ContentType.objects.get_for_model(form)
        self.assertEqual(payload["ct"], f"{ct.app_label}.{ct.model}")
        self.assertEqual(payload["oid"], str(form.pk))
