from content_editor.contents import contents_for_item
from django.conf import settings
from django.contrib.contenttypes.models import ContentType
from django.core import signing
from django.core.exceptions import ObjectDoesNotExist
from django.http import HttpResponse
from django.template import Context
from django.utils.module_loading import import_string
from django.utils.safestring import mark_safe


def resolve_ref(data):
    """
    Pop _ref from data dict, verify the signed token, and return GenericFK kwargs.

    Returns a dict with related_content_type and related_object_id if the token
    is valid, or an empty dict otherwise.
    """
    ref = data.pop("_ref", None)
    if not ref:
        return {}
    try:
        payload = signing.loads(ref)
        ct = ContentType.objects.get_by_natural_key(*payload["ct"].split("."))
        ct.get_object_for_this_type(pk=payload["oid"])
        return {
            "related_content_type": ct,
            "related_object_id": str(payload["oid"]),
        }
    except (signing.BadSignature, KeyError, ObjectDoesNotExist):
        return {}


def get_client_ip(request):
    """
    Return the client IP for the given request.

    Defaults to ``REMOTE_ADDR``, which comes from the TCP socket peer address
    and cannot be spoofed by clients. Deployments behind a proxy should set
    ``FORMBUILDER_CLIENT_IP_RESOLVER`` to a dotted path to a callable
    ``(request) -> str | None`` that consults the appropriate forwarded
    header. No forwarded header is honored by default because doing so
    without a proxy in front would let clients spoof their own IP.
    """
    resolver_path = getattr(settings, "FORMBUILDER_CLIENT_IP_RESOLVER", None)
    if resolver_path:
        return import_string(resolver_path)(request)
    return request.META.get("REMOTE_ADDR")


def create_submission(request, configured_form, data, *, submission_model):
    """
    Create a form submission record.

    Pops _ref from data and resolves it to a GenericFK if valid.
    Returns the created submission instance.
    """
    ref_kwargs = resolve_ref(data)
    return submission_model.objects.create(
        configured_form=configured_form,
        data=data,
        ip_address=get_client_ip(request),
        user_agent=request.headers.get("user-agent", ""),
        **ref_kwargs,
    )


def render_success_region(request, configured_form, *, renderer):
    """
    Render the "success" region of a configured form and return an HttpResponse.
    """
    contents = contents_for_item(configured_form, plugins=renderer.plugins())
    context = Context({"configured_form": configured_form, "request": request})
    html = mark_safe("".join(renderer.handle(contents["success"], context)))
    return HttpResponse(html)
