from admin_ordering.admin import OrderableAdmin
from content_editor.admin import deny_regions
from django.contrib import admin
from django.urls import reverse
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _
from feincms3_forms import admin as forms_admin


class FormStepInline(OrderableAdmin, admin.TabularInline):
    extra = 0
    fields = ["title", "identifier", "back_label", "next_label", "ordering"]

    @classmethod
    def for_model(cls, model):
        """Return a subclass of this inline bound to the given concrete FormStep model."""
        return type(
            f"{cls.__name__}For{model.__name__}",
            (cls,),
            {"model": model},
        )


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


class BaseFormSubmissionAdmin(admin.ModelAdmin):
    """
    Base ModelAdmin for concrete FormSubmission models.  Provides readonly
    fieldsets, ``formatted_data_display`` (calls ``get_formatted_data()``
    on the instance), ``related_object_link`` (resolves the generic FK to
    an admin change-page link), and disables add permission.

    Subclass to add project-specific actions, list filters, etc.
    """

    list_display = [
        "configured_form",
        "submitted_at",
        "ip_address",
        "related_object_link",
    ]
    list_filter = ["configured_form", "submitted_at"]
    readonly_fields = [
        "configured_form",
        "submitted_at",
        "data",
        "ip_address",
        "user_agent",
        "formatted_data_display",
        "related_object_link",
        "related_content_type",
        "related_object_id",
    ]
    fieldsets = [
        (
            None,
            {
                "fields": (
                    "configured_form",
                    "submitted_at",
                    "formatted_data_display",
                    "data",
                    "ip_address",
                    "user_agent",
                ),
            },
        ),
        (
            _("Related object"),
            {
                "fields": (
                    "related_object_link",
                    "related_content_type",
                    "related_object_id",
                ),
            },
        ),
    ]
    date_hierarchy = "submitted_at"

    @admin.display(description=_("formatted data"))
    def formatted_data_display(self, obj):
        return obj.get_formatted_data()

    @admin.display(description=_("related object"))
    def related_object_link(self, obj):
        if not obj.related_content_type_id or not obj.related_object_id:
            return "-"
        url = reverse(
            f"admin:{obj.related_content_type.app_label}_{obj.related_content_type.model}_change",
            args=[obj.related_object_id],
        )
        label = f"{obj.related_content_type.name} | {obj.related_object}"
        return format_html('<a href="{}">{}</a>', url, label)

    def has_add_permission(self, request):
        return False
