from django.shortcuts import get_object_or_404

from feincms3_formbuilder.views import multistep_form_view, simple_form_view
from testapp.models import ConfiguredForm
from testapp.renderer import renderer


def form_view(request, slug):
    configured_form = get_object_or_404(ConfiguredForm, slug=slug)
    if configured_form.form_type == "multistep":
        return multistep_form_view(request, configured_form, renderer=renderer)
    return simple_form_view(request, configured_form, renderer=renderer)
