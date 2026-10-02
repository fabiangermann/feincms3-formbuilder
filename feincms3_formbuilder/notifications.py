"""Form notifications for feincms3-formbuilder.

Public API:

- ``AbstractFormNotification`` — abstract base model.
- ``validate_recipients`` — model-level validator for the ``recipients`` field.
- ``validate_notification_recipients`` — form-level check that recipient
  variables point at email fields.
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
from feincms3_forms.models import SimpleFieldBase
from feincms3_forms.validation import Error
from html2text import html2text


logger = logging.getLogger("feincms3_formbuilder.notifications")

RECIPIENT_VARIABLE_RE = re.compile(r"\{\{\s*form_data\.(\w+)\s*\}\}")


def validate_recipients(value):
    """Validate the ``recipients`` field of a form notification."""
    value = (value or "").strip()
    if not value:
        raise ValidationError(_("Recipients must not be empty."), code="empty")

    validator = EmailValidator()
    for token in (t.strip() for t in value.split(",")):
        if not token:
            raise ValidationError(
                _("Empty email address in recipients list."),
                code="empty_token",
            )
        # A field validator cannot see the form's fields, so only the syntax of
        # a variable is checked here. Checking that it names an email field
        # requires the project to call ``validate_notification_recipients``
        # from its form type's ``validate`` function.
        if RECIPIENT_VARIABLE_RE.fullmatch(token):
            continue
        # Template syntax that EmailValidator happens to accept as an address
        # (e.g. "{{form_data.user}}@example.com") is almost certainly a mistake.
        if "{" in token or "}" in token:
            raise ValidationError(
                _(
                    "Recipients only support email addresses and"
                    " {{ form_data.<field_name> }}, without filters or tags."
                ),
                code="unsupported_template",
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


def _parse_recipients(value, form_data):
    """Resolve the ``recipients`` value into valid addresses and an invalid count.

    Variables are looked up in ``form_data`` directly instead of rendering a
    template, so a submitted value containing commas cannot add recipients.
    Invalid addresses are dropped so that one bad submitter value doesn't stop
    the notification for the remaining recipients. Raises only when no valid
    recipient is left.
    """
    validator = EmailValidator()
    recipients = []
    invalid_count = 0
    for token in (t.strip() for t in value.split(",")):
        if match := RECIPIENT_VARIABLE_RE.fullmatch(token):
            address = str(form_data.get(match[1]) or "").strip()
        else:
            address = token
        if not address:
            continue
        try:
            validator(address)
        except ValidationError:
            invalid_count += 1
        else:
            recipients.append(address)
    if not recipients:
        raise ValidationError(
            "No valid recipients.", code="no_recipients",
        )
    return recipients, invalid_count


def _send_one(notification, context):
    text_ctx = Context(context, autoescape=False)
    html_ctx = Context(context, autoescape=True)

    rendered_subject = Template(notification.subject).render(text_ctx)
    rendered_html = Template(notification.body).render(html_ctx)
    rendered_text = html2text(rendered_html)

    recipients, invalid_count = _parse_recipients(
        notification.recipients, context.get("form_data") or {},
    )
    if invalid_count:
        # ERROR rather than WARNING so error trackers still report the
        # dropped recipients.
        logger.error(
            "Skipped %d invalid recipient(s) of notification %r",
            invalid_count, notification,
        )
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
    available to the templates rendered for ``subject`` and ``body``.
    ``recipients`` only resolves ``{{ form_data.<field_name> }}`` from
    ``context["form_data"]``.

    On any per-notification failure (template error, no valid rendered
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


def validate_notification_recipients(
    configured_form,
    renderer,
    notifications,
    *,
    email_field_types=(SimpleFieldBase.Type.EMAIL,),
):
    """Check that ``{{ form_data.<name> }}`` in recipients names an email field.

    ``validate_recipients`` only checks the syntax of these variables because
    a field validator cannot see the form's fields. Without this check, a reference to
    a missing or non-email field only fails at send time, when the submitter's
    notification is silently dropped. Call it from the form type's
    ``validate`` function; the admin shows the returned errors after saving.

    ``email_field_types`` lists the field ``type`` values that count as email
    fields. Custom field plugins have their lowercased class name as type.
    """
    field_types = {
        name: attributes["type"]
        for name, attributes in configured_form.get_formfields_union(
            plugins=renderer.plugins(), attributes=["type"],
        )
    }
    errors = []
    for notification in notifications:
        for name in RECIPIENT_VARIABLE_RE.findall(notification.recipients):
            if name not in field_types:
                message = _(
                    "Notification \"{notification}\": recipients refer to"
                    " field '{name}', which does not exist."
                )
            elif field_types[name] not in email_field_types:
                message = _(
                    "Notification \"{notification}\": recipients refer to"
                    " field '{name}', which is not an email address field."
                )
            else:
                continue
            errors.append(
                Error(message.format(notification=notification, name=name))
            )
    return errors
