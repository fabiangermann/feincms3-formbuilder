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

from feincms3_formbuilder.models import ConditionalFieldMixin


logger = logging.getLogger("feincms3_formbuilder.conditionals")

_CONTROLLING_TYPES = {SimpleFieldBase.Type.SELECT, SimpleFieldBase.Type.RADIO}


def _get_condition(plugin):
    """Return ``(controlling field name, values)``, or ``None`` if unconditional.

    Only plugins with ``ConditionalFieldMixin`` can carry a condition; a
    project may register field plugins that never opted in, and an unrelated
    ``show_when_field`` attribute on one of them must not turn it conditional.
    """
    if not isinstance(plugin, ConditionalFieldMixin) or not plugin.show_when_field:
        return None
    return (plugin.show_when_field, plugin.show_when_values_list)


def _controlling_value(name, data):
    """Return the controlling field's answer as the key that conditions compare
    against, ``""`` when unanswered.

    The single place that turns a raw answer into that key, whatever the
    source: a POST ``QueryDict``, the multistep session dict, or a merge of
    both. For select and radio fields the submitted value already is the key.
    New controlling types change this function (checkboxes, multi-selects,
    text, date and number fields).
    """
    value = data.get(name)
    return "" if value is None else str(value)


def _is_active(condition, data):
    """Whether a field carrying ``condition`` applies to the available data.

    An unconditional field (``condition is None``) is always active; so is any
    caller that forgets to look one up.
    """
    if condition is None:
        return True
    name, values = condition
    return _controlling_value(name, data) in values


@dataclasses.dataclass
class ResolvedConditionals:
    """What ``create_form_with_conditionals`` decided about a form's
    conditionals, attached to the form as ``form._f3fb_conditionals``.

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
    """Build the form from ``plugins`` and resolve its conditionals.

    Every argument except ``available_data`` goes straight to feincms3-forms'
    ``create_form``. ``available_data`` is what the conditions are evaluated
    against. It defaults to ``form.data`` for a bound form and ``form.initial``
    otherwise. Pass it when a controlling answer lives outside the form, as on
    a multistep step POST whose controlling field is on an earlier step.

    Inactive conditionals stay in the form: hidden, not required, disabled,
    and dropped in ``clean()``.
    """
    form = create_form(plugins, form_class=form_class, form_kwargs=form_kwargs)
    if available_data is None:
        available_data = form.data if form.is_bound else form.initial

    resolved = ResolvedConditionals(inactive=set(), conditions={})
    form._f3fb_conditionals = resolved

    field_plugins = [p for p in plugins if isinstance(p, FormFieldBase)]
    types = {p.name: getattr(p, "type", "") for p in field_plugins}

    for plugin in field_plugins:
        condition = _get_condition(plugin)
        if condition is None:
            continue
        name, values = condition
        if name in types and types[name] not in _CONTROLLING_TYPES:
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
            active = _is_active(condition, available_data)

        resolved.conditions[plugin] = {
            "field": name,
            "values": json.dumps(values),
            "active": active,
        }

        if active:
            continue

        # A plugin may contribute several form fields; the condition applies
        # to all of them.
        for field_name in form.get_form_fields(plugin):
            resolved.inactive.add(field_name)
            field = form.fields[field_name]
            if field.required:
                field.widget.attrs["data-required"] = True
                field.required = False
            # Not ``field.disabled``: that makes Django ignore submitted data in
            # favour of initial, which breaks the no-JavaScript round-trip.
            field.widget.attrs["disabled"] = True

    if resolved.inactive:
        form._f3f_cleaners.append(_drop_inactive)
    return form


def condition_context(form, plugin):
    """Return ``plugin``'s condition for a template, or ``{}``.

    Returns ``{}`` both for unconditional plugins and for forms built with
    feincms3-forms' ``create_form`` directly, so a project's own renderer works
    either way.
    """
    resolved = getattr(form, "_f3fb_conditionals", None)
    if resolved is None:
        return {}
    return resolved.conditions.get(plugin, {})
