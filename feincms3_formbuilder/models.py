from admin_ordering.models import OrderableModel
from content_editor.models import Region
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError
from django.core.serializers.json import DjangoJSONEncoder
from django.db import models
from django.utils.crypto import get_random_string
from django.utils.translation import gettext_lazy as _
from feincms3_forms import models as forms_models
from feincms3_forms.reporting import simple_report
from feincms3_forms.validation import validate_uniqueness


STEP_REGION_PREFIX = "step_"


class StepSlugField(models.CharField):
    def deconstruct(self):
        name, _path, args, kwargs = super().deconstruct()
        return name, "django.db.models.CharField", args, kwargs

    def formfield(self, **kwargs):
        kwargs.setdefault("required", False)
        return super().formfield(**kwargs)

    def to_python(self, value):
        value = super().to_python(value)
        if not value:
            return get_random_string(
                10, allowed_chars="abcdefghijklmnopqrstuvwxyz0123456789"
            )
        if not f"{STEP_REGION_PREFIX}{value}".isidentifier():
            raise ValidationError(
                _("%(value)s is not a valid region key identifier."),
                params={"value": value},
            )
        return value

    def pre_save(self, model_instance, add):
        value = getattr(model_instance, self.attname)
        if not value:
            value = get_random_string(
                10, allowed_chars="abcdefghijklmnopqrstuvwxyz0123456789"
            )
            setattr(model_instance, self.attname, value)
        return value


class AbstractFormStep(OrderableModel):
    title = models.CharField(_("title"), max_length=200)
    identifier = StepSlugField(_("identifier"), max_length=100, blank=True)
    created_at = models.DateTimeField(_("created at"), auto_now_add=True)
    updated_at = models.DateTimeField(_("updated at"), auto_now=True)

    class Meta(OrderableModel.Meta):
        abstract = True
        verbose_name = _("form step")
        verbose_name_plural = _("form steps")

    def __str__(self):
        return self.title

    @property
    def region_key(self):
        return f"{STEP_REGION_PREFIX}{self.identifier}"


def validate_with_renderer(configured_form, renderer):
    """
    Validate a configured form using the given renderer's plugins.
    Helper for projects to use in their custom validate functions.
    """
    fields = configured_form.get_formfields_union(
        plugins=renderer.plugins(),
        attributes=["name"],
    )
    return list(validate_uniqueness(fields))


def _default_validate(configured_form):
    """
    Default no-op validator. Projects should override FORMS to point validate
    to a function that calls validate_with_renderer with their renderer.
    """
    return []


def _not_implemented_process(request, form, **kwargs):
    raise NotImplementedError(
        "Subclasses must override FORMS to provide a process function."
    )


class AbstractConfiguredForm(forms_models.ConfiguredForm):
    created_at = models.DateTimeField(_("created at"), auto_now_add=True)
    updated_at = models.DateTimeField(_("updated at"), auto_now=True)

    FORMS = [
        forms_models.FormType(
            key="simple",
            label=_("simple form"),
            regions=[
                Region(key="form", title=_("Form fields")),
                Region(key="success", title=_("Success message")),
            ],
            form_class="django.forms.Form",
            validate="feincms3_formbuilder.models._default_validate",
            process="feincms3_formbuilder.models._not_implemented_process",
        ),
        forms_models.FormType(
            key="multistep",
            label=_("multi-step form"),
            regions=lambda configured_form: (
                (
                    [
                        Region(key=step.region_key, title=step.title)
                        for step in configured_form.steps.all()
                    ]
                    if configured_form.pk
                    else []
                )
                + [Region(key="success", title=_("Success message"))]
            ),
            form_class="django.forms.Form",
            validate="feincms3_formbuilder.models._default_validate",
            process="feincms3_formbuilder.models._not_implemented_process",
        ),
    ]

    class Meta:
        abstract = True
        verbose_name = _("configured form")
        verbose_name_plural = _("configured forms")
        ordering = ["-created_at"]

    def __str__(self):
        return self.name


class FormSubmissionQuerySet(models.QuerySet):
    def for_related_object(self, obj):
        content_type = ContentType.objects.get_for_model(obj)
        return self.filter(
            related_content_type=content_type,
            related_object_id=str(obj.pk),
        )


class AbstractFormSubmission(models.Model):
    submitted_at = models.DateTimeField(_("submitted at"), auto_now_add=True)
    data = models.JSONField(_("data"), encoder=DjangoJSONEncoder)
    ip_address = models.GenericIPAddressField(_("IP address"), blank=True, null=True)
    user_agent = models.TextField(_("user agent"), blank=True)

    related_content_type = models.ForeignKey(
        ContentType,
        on_delete=models.CASCADE,
        blank=True,
        null=True,
        verbose_name=_("related content type"),
    )
    related_object_id = models.CharField(max_length=255, blank=True)
    related_object = GenericForeignKey("related_content_type", "related_object_id")

    objects = FormSubmissionQuerySet.as_manager()

    class Meta:
        abstract = True
        verbose_name = _("form submission")
        verbose_name_plural = _("form submissions")
        ordering = ["-submitted_at"]

    def __str__(self):
        return f"{self.configured_form} - {self.submitted_at}"

    def get_formatted_data(self, *, field_model=None):
        if field_model is None:
            raise NotImplementedError(
                "Pass field_model or override get_formatted_data in your subclass."
            )
        form_fields = field_model.objects.filter(
            parent=self.configured_form,
        ).order_by("ordering")
        return simple_report(contents=list(form_fields), data=self.data)
