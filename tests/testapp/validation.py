from feincms3_formbuilder.models import validate_with_renderer
from testapp.renderer import renderer


def validate_configured_form(configured_form):
    return validate_with_renderer(configured_form, renderer)
