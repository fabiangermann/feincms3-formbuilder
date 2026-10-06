"""Conditional form fields for feincms3-formbuilder.

A *condition* is the rule configured on a field plugin: the name of a
controlling field plus the values that satisfy it.  The *conditionals* are the
fields that have one.

A conditional is active when the data available at the moment the form is built
satisfies its condition.  That is the whole rule: the logic never asks which
step a field is on, whether its controlling field is in the same form, or
whether the browser can see it.  An unanswered controlling field is simply not
a match, which is what makes conditions across steps work with no extra code.

Public API:

- ``create_form_with_conditionals`` — build a form with its conditionals
  resolved.
- ``condition_context`` — the template context a renderer needs to emit a
  condition as data attributes.
- ``validate_conditionals`` — editor-time check for the form type's
  ``validate`` function.
"""

import dataclasses
import json
import logging

from django import forms
from feincms3_forms.models import FormFieldBase, SimpleFieldBase
from feincms3_forms.renderer import create_form


logger = logging.getLogger("feincms3_formbuilder.conditionals")

CONTROLLING_TYPES = {SimpleFieldBase.Type.SELECT, SimpleFieldBase.Type.RADIO}


def get_condition(plugin):
    """Return ``(controlling field name, values)``, or ``None`` if unconditional.

    Tolerates plugins without ``ConditionalFieldMixin``: a project may register
    field plugins that never opted into conditions.
    """
    name = getattr(plugin, "show_when_field", "")
    if not name:
        return None
    return (name, plugin.show_when_values_list)


def controlling_value(name, data):
    """Return the controlling field's answer as a string, ``""`` when unanswered.

    ``data`` may be a POST ``QueryDict``, the multistep session dict, or a
    merge of both; ``.get()`` behaves the same on all three for the
    single-valued select and radio fields that are allowed to control other
    fields.
    """
    value = data.get(name)
    return "" if value is None else str(value)


def is_active(condition, data):
    """Whether a field carrying ``condition`` applies to the available data.

    An unconditional field (``condition is None``) is always active; so is any
    caller that forgets to look one up.
    """
    if condition is None:
        return True
    name, values = condition
    return controlling_value(name, data) in values


@dataclasses.dataclass
class FormConditionals:
    """What a built form knows about its conditionals.

    ``inactive`` holds form field names, not plugins, because that is what the
    cleaner and the stale-value filter in ``views.py`` work with; ``conditions``
    is keyed by plugin because that is what a renderer has in hand.
    """

    inactive: set
    conditions: dict


def _drop_inactive(form, data):
    """Remove inactive conditionals from ``cleaned_data`` and from the errors.

    Runs as a ``create_form`` cleaner, i.e. from ``clean()``. Errors are popped
    rather than prevented because ``required`` and the field validators run in
    ``_clean_fields()``, before ``clean()`` is reached. An inactive field must
    never block a submission — the user cannot see it to fix it.
    """
    for name in form._f3fb_conditionals.inactive:
        data.pop(name, None)
        form._errors.pop(name, None)
    return data


def create_form_with_conditionals(
    plugins, *, form_class=forms.Form, form_kwargs, available_data=None
):
    """Build the form for ``plugins`` with every conditional resolved.

    ``plugins``, ``form_class`` and ``form_kwargs`` go straight to
    feincms3-forms' ``create_form``; ``available_data`` is the only addition.
    Omit it and the form's own data is used — ``form.data`` when bound,
    ``form.initial`` when not — which is correct at every call site except a
    multistep step POST, where the controlling field may sit on an earlier step
    and only the session holds its answer.

    Inactive conditionals stay in the form. They are rendered hidden by the
    template, stop being required, carry ``disabled`` inputs, and lose their
    value in ``clean()``.
    """
    form = create_form(plugins, form_class=form_class, form_kwargs=form_kwargs)
    if available_data is None:
        available_data = form.data if form.is_bound else form.initial

    state = FormConditionals(inactive=set(), conditions={})
    form._f3fb_conditionals = state

    field_plugins = [p for p in plugins if isinstance(p, FormFieldBase)]
    types = {p.name: getattr(p, "type", "") for p in field_plugins}

    for plugin in field_plugins:
        condition = get_condition(plugin)
        if condition is None:
            continue
        name, values = condition
        if name in types and types[name] not in CONTROLLING_TYPES:
            # Only decidable for a controlling field in this very form; every
            # other misconfiguration is the editor-time check's job.
            logger.warning(
                "Field %r is controlled by %r, which is not a dropdown or a"
                " radio field. It will never be shown.",
                plugin.name,
                name,
            )
            active = False
        else:
            active = is_active(condition, available_data)

        state.conditions[plugin] = {
            "field": name,
            "values": json.dumps(values),
            "active": active,
        }
        if active:
            continue

        for field_name in form.get_form_fields(plugin):
            state.inactive.add(field_name)
            field = form.fields[field_name]
            if field.required:
                field.widget.attrs["data-required"] = True
                field.required = False
            # Not ``field.disabled``: that makes Django ignore submitted data in
            # favour of initial, which breaks the no-JavaScript round-trip.
            field.widget.attrs["disabled"] = True

    if state.inactive:
        form._f3f_cleaners.append(_drop_inactive)
    return form


def condition_context(form, plugin):
    """Return ``plugin``'s condition for a template, or ``{}``.

    Returns ``{}`` both for unconditional plugins and for forms built with
    feincms3-forms' ``create_form`` directly, so a project's own renderer works
    either way.
    """
    state = getattr(form, "_f3fb_conditionals", None)
    if state is None:
        return {}
    return state.conditions.get(plugin, {})
