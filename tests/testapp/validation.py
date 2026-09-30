from feincms3_formbuilder.models import validate_with_renderer
from feincms3_formbuilder.notifications import validate_notification_recipients
from testapp.renderer import renderer


def validate_configured_form(configured_form):
    return [
        *validate_with_renderer(configured_form, renderer),
        *validate_notification_recipients(
            configured_form, renderer, configured_form.notifications.all(),
        ),
    ]
