"""Form notifications for feincms3-formbuilder.

Public API:

- ``AbstractFormNotification`` — abstract base model.
- ``validate_recipients`` — model-level validator for the ``recipients`` field.
- ``send_form_notifications`` — render and send notifications using a context dict.
"""

import re

from django.core.exceptions import ValidationError
from django.core.validators import EmailValidator
from django.db import models
from django.utils.translation import gettext_lazy as _


VARIABLE_RE = re.compile(r"\{\{.*?\}\}")


def validate_recipients(value):
    """Validate the ``recipients`` field of a form notification."""
    value = (value or "").strip()
    if not value:
        raise ValidationError(_("Recipients must not be empty."), code="empty")

    if VARIABLE_RE.search(value):
        return

    validator = EmailValidator()
    for token in (t.strip() for t in value.split(",")):
        if not token:
            raise ValidationError(
                _("Empty email address in recipients list."),
                code="empty_token",
            )
        validator(token)


class AbstractFormNotification(models.Model):
    recipients = models.CharField(
        _("recipients"), max_length=500, validators=[validate_recipients],
    )
    subject = models.CharField(_("subject"), max_length=500)
    body = models.TextField(_("body"), help_text=_(
        "HTML. Supports {{ form_data.<field_name> }} and any keys the project "
        "places in the notification context."
    ))

    class Meta:
        abstract = True
        verbose_name = _("form notification")
        verbose_name_plural = _("form notifications")

    def __str__(self):
        return self.subject
