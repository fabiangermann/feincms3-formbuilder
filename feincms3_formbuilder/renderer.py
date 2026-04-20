from feincms3 import renderer as _feincms3_renderer
from feincms3.renderer import RegionRenderer, render_in_context


def render_form_field(plugin, context):
    """Render a form field plugin using the form object from context."""
    form = context.get("form")
    if not form:
        return ""
    fields = form.get_form_fields(plugin)
    return render_in_context(
        context,
        "feincms3_formbuilder/form_field.html",
        {"plugin": plugin, "fields": fields},
    )


def create_form_renderer(*field_models, extra_plugins=None):
    """
    Create a RegionRenderer pre-configured for form field rendering.

    Each model in field_models is registered with render_form_field.
    extra_plugins is an optional dict mapping model -> renderer callable.
    """
    renderer = RegionRenderer()
    for model in field_models:
        renderer.register(model, render_form_field)
    if extra_plugins:
        for model, renderer_func in extra_plugins.items():
            if hasattr(model, "_meta"):
                renderer.register(model, renderer_func)
            else:
                # Non-Django-model plugin: bypass the _meta check by inserting directly
                renderer._plugins[model] = (
                    model,
                    renderer_func,
                    "default",
                    _feincms3_renderer._default_marks,
                    True,
                )
    return renderer
