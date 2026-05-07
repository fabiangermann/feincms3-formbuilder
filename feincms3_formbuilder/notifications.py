"""Form notifications for feincms3-formbuilder.

Public API:

- ``AbstractFormNotification`` — abstract base model.
- ``validate_recipients`` — model-level validator for the ``recipients`` field.
- ``send_form_notifications`` — render and send notifications using a context dict.
"""

import logging
import re

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.mail import EmailMultiAlternatives
from django.core.validators import EmailValidator
from django.db import models
from django.template import Context, Template
from django.utils.translation import gettext_lazy as _
from html2text import html2text


logger = logging.getLogger("feincms3_formbuilder.notifications")

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


def _parse_recipients(rendered):
    validator = EmailValidator()
    recipients = []
    for token in (t.strip() for t in rendered.split(",")):
        if not token:
            continue
        validator(token)
        recipients.append(token)
    if not recipients:
        raise ValidationError(
            "No recipients after rendering.", code="no_recipients",
        )
    return recipients


def _send_one(notification, context):
    text_ctx = Context(context, autoescape=False)
    html_ctx = Context(context, autoescape=True)

    rendered_recipients = Template(notification.recipients).render(text_ctx)
    rendered_subject = Template(notification.subject).render(text_ctx)
    rendered_html = Template(notification.body).render(html_ctx)
    rendered_text = html2text(rendered_html)

    recipients = _parse_recipients(rendered_recipients)
    from_email = (
        getattr(settings, "FORMBUILDER_FROM_EMAIL", None)
        or settings.DEFAULT_FROM_EMAIL
    )

    message = EmailMultiAlternatives(
        subject=rendered_subject.strip(),
        body=rendered_text,
        from_email=from_email,
        to=recipients,
    )
    message.attach_alternative(rendered_html, "text/html")
    message.send()


def send_form_notifications(
    notifications, *, context, fail_silently=True, send_one=None,
):
    """Render and send each notification using the given context dict.

    ``notifications`` is any iterable of ``AbstractFormNotification``
    subclass instances. ``context`` is a plain dict of variables made
    available to the templates rendered for ``recipients``, ``subject``,
    and ``body``.

    On any per-notification failure (template error, invalid rendered
    recipient, SMTP error), logs the failure at ``ERROR`` and continues
    with the remaining notifications when ``fail_silently`` is ``True``
    (the default), or re-raises when ``False``.

    Pass ``send_one=callable`` to override the default per-notification
    send function — useful when projects extend
    ``AbstractFormNotification`` with extra fields (e.g. ``reply_to``).
    """
    send_one = send_one or _send_one
    for notification in notifications:
        try:
            send_one(notification, context)
        except Exception:
            logger.exception(
                "Failed to send notification %r", notification,
            )
            if not fail_silently:
                raise
