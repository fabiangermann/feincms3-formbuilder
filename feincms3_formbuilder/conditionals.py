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

import logging

from feincms3_forms.models import SimpleFieldBase


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
