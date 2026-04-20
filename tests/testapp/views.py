from django.shortcuts import get_object_or_404

from feincms3_formbuilder.views import form_view_router

from testapp.models import ConfiguredForm
from testapp.renderer import renderer


def form_view(request, slug):
    configured_form = get_object_or_404(ConfiguredForm, slug=slug)
    return form_view_router(request, configured_form, renderer=renderer)
