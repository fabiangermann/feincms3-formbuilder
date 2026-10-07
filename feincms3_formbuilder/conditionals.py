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

from content_editor.contents import contents_for_item
from django import forms
from django.utils.translation import gettext as _
from feincms3_forms.models import FormFieldBase, SimpleFieldBase
from feincms3_forms.renderer import create_form
from feincms3_forms.validation import Error

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

        # A plugin may contribute several form fields; the condition applies
        # to all of them.
        for field_name in form.get_form_fields(plugin):
            field = form.fields[field_name]
            # Only where Django would render the HTML ``required``: it never
            # does on multiple checkboxes, and a script setting it there would
            # make the browser demand every box. Not
            # ``BoundField.build_widget_attrs()``: it reads ``errors`` and so
            # validates the form before it is set up.
            if (
                field.required
                and form.use_required_attribute
                and field.widget.use_required_attribute(form[field_name].initial)
            ):
                field.widget.attrs["data-required-if-active"] = True
            if active:
                continue

            resolved.inactive.add(field_name)
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


def validate_conditionals(configured_form, renderer):
    """Report misconfigured conditions to the editor after saving.

    Returns feincms3-forms ``Error`` instances for the form type's ``validate``
    function, like ``validate_notification_recipients``. At runtime a
    misconfigured condition simply never matches, so the field is never shown
    and nothing explains why, which is what makes this check worth the code.
    """
    contents = contents_for_item(configured_form, plugins=renderer.plugins())
    region_order = {
        region.key: index for index, region in enumerate(configured_form.regions)
    }

    plugins = []
    for region in configured_form.regions:
        for plugin in contents[region.key]:
            if isinstance(plugin, FormFieldBase):
                plugins.append(plugin)
    by_name = {plugin.name: plugin for plugin in plugins}

    errors = []
    for plugin in plugins:
        condition = _get_condition(plugin)
        if condition is None:
            continue
        name, values = condition

        if name == plugin.name:
            errors.append(
                Error(
                    _("Field '%(field)s' is configured to depend on itself.")
                    % {"field": plugin.name}
                )
            )
            continue

        control = by_name.get(name)
        if control is None:
            errors.append(
                Error(
                    _("Field '%(field)s' depends on '%(control)s', which doesn't exist.")
                    % {"field": plugin.name, "control": name}
                )
            )
            continue

        if getattr(control, "type", "") not in _CONTROLLING_TYPES:
            errors.append(
                Error(
                    _(
                        "Field '%(field)s' depends on '%(control)s', which is not a"
                        " dropdown or a radio field."
                    )
                    % {"field": plugin.name, "control": name}
                )
            )
            continue

        if _get_condition(control) is not None:
            errors.append(
                Error(
                    _(
                        "Field '%(field)s' depends on '%(control)s', which is itself"
                        " conditional. Chained conditions are not supported."
                    )
                    % {"field": plugin.name, "control": name}
                )
            )

        if region_order.get(control.region, 0) > region_order.get(plugin.region, 0):
            errors.append(
                Error(
                    _(
                        "Field '%(field)s' depends on '%(control)s', which is asked on"
                        " a later step. It would never be shown."
                    )
                    % {"field": plugin.name, "control": name}
                )
            )

        if not values:
            errors.append(
                Error(
                    _("Field '%(field)s' has a controlling field but no values.")
                    % {"field": plugin.name}
                )
            )
            continue

        choice_keys = [key for key, _label in control.get_choices()]
        if unknown := [value for value in values if value not in choice_keys]:
            # Listing the keys matters because editors tend to type the label
            # (``Phone``) where the submitted key (``phone``) is needed.
            errors.append(
                Error(
                    _(
                        "Field '%(field)s' is shown for %(values)s, which"
                        " '%(control)s' doesn't offer. Valid values: %(keys)s."
                    )
                    % {
                        "field": plugin.name,
                        "control": name,
                        "values": ", ".join(f"'{value}'" for value in sorted(unknown)),
                        "keys": ", ".join(choice_keys),
                    }
                )
            )

    return errors
