from django.test import TestCase

from feincms3_formbuilder.renderer import create_form_renderer

from testapp.models import RichText, SimpleField


class CreateFormRendererTest(TestCase):
    def test_creates_renderer_with_field_models(self):
        renderer = create_form_renderer(SimpleField)
        plugins = renderer.plugins()
        self.assertIn(SimpleField, plugins)

    def test_creates_renderer_with_extra_plugins(self):
        def dummy_renderer(plugin, context):
            return "dummy"

        renderer = create_form_renderer(
            SimpleField,
            extra_plugins={RichText: dummy_renderer},
        )
        plugins = renderer.plugins()
        self.assertIn(SimpleField, plugins)
        self.assertIn(RichText, plugins)
