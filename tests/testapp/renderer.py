from feincms3.renderer import template_renderer
from feincms3_formbuilder.renderer import create_form_renderer

from testapp.models import RichText, SimpleField

renderer = create_form_renderer(
    SimpleField,
    extra_plugins={
        RichText: template_renderer("testapp/richtext.html"),
    },
)
