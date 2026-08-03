from content_editor.contents import contents_for_item
from django.core.exceptions import ImproperlyConfigured
from django.utils.text import capfirst
from feincms3_forms.models import FormFieldBase
from feincms3_forms.reporting import get_loaders


try:
    from xlsxdocument import XLSXDocument
except ImportError:  # pragma: no cover
    XLSXDocument = None


# Characters Excel forbids in worksheet titles; openpyxl raises on any of them.
_INVALID_SHEET_CHARS = str.maketrans(dict.fromkeys(r"[]:*?/" + "\\", " "))
_MAX_SHEET_TITLE = 31


def _sheet_title(name, used):
    """Return a unique, Excel-safe worksheet title derived from ``name``.

    openpyxl raises when a sheet title contains ``[ ] : * ? / \\``, exceeds 31
    characters, or duplicates an existing title. Callers pass a shared ``used``
    set so collisions across forms (including ones that only collide after
    truncation) get a numeric suffix.
    """
    title = name.translate(_INVALID_SHEET_CHARS).strip()[:_MAX_SHEET_TITLE] or "Sheet"
    candidate = title
    counter = 2
    while candidate.casefold() in used:
        suffix = f" ({counter})"
        candidate = f"{title[: _MAX_SHEET_TITLE - len(suffix)]}{suffix}"
        counter += 1
    used.add(candidate.casefold())
    return candidate


def _metadata_cells(submission):
    """Leading (non-field) columns for a submission row.

    Labels follow the model's own field ``verbose_name``s.
    """
    meta = submission._meta
    return [
        {"label": capfirst(meta.pk.verbose_name), "name": "", "value": submission.pk},
        {
            "label": capfirst(meta.get_field("submitted_at").verbose_name),
            "name": "",
            "value": submission.submitted_at,
        },
        {
            "label": capfirst(meta.get_field("ip_address").verbose_name),
            "name": "",
            "value": submission.ip_address or "",
        },
        {
            "label": capfirst(meta.get_field("user_agent").verbose_name),
            "name": "",
            "value": submission.user_agent or "",
        },
    ]


def build_submissions_xlsx(queryset, *, renderer) -> "XLSXDocument":
    """Build an XLSXDocument from a FormSubmission queryset.

    Submissions are grouped by configured form; each form gets its own sheet
    named after the form. Columns are the metadata columns (ID, submitted at,
    IP address, user agent) followed by one column per form field.

    Field columns iterate via ``contents_for_item`` so every ``FormFieldBase``
    plugin the ``renderer`` knows about participates, and columns are grouped by
    region in ``ConfiguredForm.regions`` order and sorted by ``ordering`` within
    each region. Region order is the order the regions are declared on the
    ``FormType``; for the ``simple`` and ``multistep`` form types this is the
    order the user filled the form in, but it is not guaranteed to match the
    visual order for arbitrary custom form types.

    ``renderer`` is the project's form renderer; it is required because the set
    of plugin models is inherently per-project. Raises ``ImproperlyConfigured``
    if the optional ``xlsxdocument`` dependency is not installed.
    """
    if XLSXDocument is None:
        raise ImproperlyConfigured(
            "build_submissions_xlsx requires the 'xlsxdocument' package. "
            "Install it via the extra: pip install feincms3-formbuilder[xlsx]."
        )

    submissions = list(queryset.select_related("configured_form"))
    plugins = renderer.plugins()

    cf_loaders = {}
    for cf in {sub.configured_form for sub in submissions}:
        contents = contents_for_item(cf, plugins)
        fields = [plugin for plugin in contents if isinstance(plugin, FormFieldBase)]
        cf_loaders[cf] = get_loaders(fields)

    cf_values = {}
    for submission in submissions:
        line = _metadata_cells(submission) + [
            loader(submission.data)
            for loader in cf_loaders[submission.configured_form]
        ]
        if submission.configured_form not in cf_values:
            cf_values[submission.configured_form] = [[cell["label"] for cell in line]]
        cf_values[submission.configured_form].append([cell["value"] for cell in line])

    xlsx = XLSXDocument()
    used_titles = set()
    for configured_form, values in cf_values.items():
        xlsx.add_sheet(_sheet_title(str(configured_form), used_titles))
        xlsx.table(None, values)
    return xlsx
