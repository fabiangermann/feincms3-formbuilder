from admin_ordering.admin import OrderableAdmin
from content_editor.admin import deny_regions
from django.contrib import admin
from feincms3_forms import admin as forms_admin


class FormStepInline(OrderableAdmin, admin.TabularInline):
    extra = 0
    fields = ["title", "identifier", "ordering"]


def simple_field_inlines(model):
    """
    Return a list of 11 SimpleFieldInline.create() calls for all standard
    field types, with material icons and deny_regions({"success"}).
    """
    type_configs = [
        (model.proxy(model.Type.TEXT), '<span class="material-icons">short_text</span>'),
        (model.proxy(model.Type.EMAIL), '<span class="material-icons">alternate_email</span>'),
        (model.proxy(model.Type.URL), '<span class="material-icons">link</span>'),
        (model.proxy(model.Type.DATE), '<span class="material-icons">event</span>'),
        (model.proxy(model.Type.INTEGER), '<span class="material-icons">looks_one</span>'),
        (model.proxy(model.Type.TEXTAREA), '<span class="material-icons">notes</span>'),
        (model.proxy(model.Type.CHECKBOX), '<span class="material-icons">check_box</span>'),
        (model.proxy(model.Type.SELECT), '<span class="material-icons">arrow_drop_down_circle</span>'),
        (model.proxy(model.Type.RADIO), '<span class="material-icons">radio_button_checked</span>'),
        (model.proxy(model.Type.SELECT_MULTIPLE), '<span class="material-icons">checklist</span>'),
        (model.proxy(model.Type.CHECKBOX_SELECT_MULTIPLE), '<span class="material-icons">library_add_check</span>'),
    ]

    return [
        forms_admin.SimpleFieldInline.create(
            model=proxy_model,
            button=icon,
            regions=deny_regions({"success"}),
        )
        for proxy_model, icon in type_configs
    ]
