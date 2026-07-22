from django.apps import AppConfig
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.utils.module_loading import import_string
from django.utils.text import capfirst
from django.utils.translation import gettext_lazy as _


class FeinCMS3FormbuilderConfig(AppConfig):
    name = "feincms3_formbuilder"
    verbose_name = capfirst(_("feincms3 formbuilder"))

    def ready(self):
        """
        Validate pluggable-setting dotted paths at startup so a bad
        configuration fails at deploy time rather than 500ing on the first
        form submission.
        """
        resolver_path = getattr(settings, "FORMBUILDER_CLIENT_IP_RESOLVER", None)
        if resolver_path:
            try:
                import_string(resolver_path)
            except ImportError as exc:
                raise ImproperlyConfigured(
                    f"FORMBUILDER_CLIENT_IP_RESOLVER = {resolver_path!r} "
                    f"could not be imported: {exc}"
                ) from exc
