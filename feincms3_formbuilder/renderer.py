from feincms3.renderer import RegionRenderer, render_in_context

from feincms3_formbuilder.conditionals import condition_context


def render_form_field(plugin, context):
    """Render a form field plugin using the form object from context.

    ``condition`` carries the plugin's show-when rule so the template can emit
    it for the browser and hide the field when the server considers it
    inactive.
    """
    form = context.get("form")
    if not form:
        return ""
    fields = form.get_form_fields(plugin)
    return render_in_context(
        context,
        "feincms3_formbuilder/form_field.html",
        {
            "plugin": plugin,
            "fields": fields,
            "condition": condition_context(form, plugin),
        },
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
            renderer.register(model, renderer_func)
    return renderer
