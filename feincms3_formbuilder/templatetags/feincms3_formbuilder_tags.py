from django import template
from django.contrib.contenttypes.models import ContentType
from django.core import signing

register = template.Library()


@register.filter
def make_submission_ref(obj):
    ct = ContentType.objects.get_for_model(obj)
    return signing.dumps({"ct": f"{ct.app_label}.{ct.model}", "oid": str(obj.pk)})
