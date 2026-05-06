import json

from content_editor.contents import contents_for_item
from django import forms
from django.core.serializers.json import DjangoJSONEncoder
from django.shortcuts import render
from django.template import Context
from django.utils.safestring import mark_safe
from feincms3_forms.renderer import create_form

from feincms3_formbuilder.models import STEP_REGION_PREFIX


def _render_region_content(contents, region_key, context, *, renderer):
    """Render non-field plugins from a region."""
    return mark_safe("".join(renderer.handle(contents[region_key], context)))


def _ref_initial(request):
    """Return ``{"_ref": <token>}`` if ``?ref=`` is present, else ``{}``.

    Pairs with the ``make_submission_ref`` template filter and the
    ``resolve_ref`` processing helper to link a submission back to a related
    object.  If the consuming form_class has no ``_ref`` field the value is
    silently ignored by Django's form initial handling.
    """
    if ref := request.GET.get("ref"):
        return {"_ref": ref}
    return {}


def simple_form_view(request, configured_form, *, renderer, form_class=None):
    """Handle simple form display and submission."""
    if form_class is None:
        form_class = configured_form.type.form_class
    contents = contents_for_item(configured_form, plugins=renderer.plugins())

    if request.method == "POST":
        form = create_form(
            contents["form"],
            form_class=form_class,
            form_kwargs={"data": request.POST, "files": request.FILES},
        )
        if form.is_valid():
            return configured_form.type.process(
                request, form, configured_form=configured_form
            )
    else:
        form = create_form(
            contents["form"],
            form_class=form_class,
            form_kwargs={"initial": _ref_initial(request)},
        )

    context = Context({"request": request, "form": form})
    form_content = _render_region_content(contents, "form", context, renderer=renderer)

    return render(
        request,
        "feincms3_formbuilder/form.html",
        {
            "configured_form": configured_form,
            "form": form,
            "form_content": form_content,
        },
    )


def get_session_data(request, configured_form):
    """Get or initialize session data for a multistep form."""
    session_key = f"multistep_form_{configured_form.pk}"
    raw = request.session.get(session_key)
    if raw is None:
        return {"step": 0, "data": {}}
    if isinstance(raw, dict):
        return raw
    return json.loads(raw)


def save_session_data(request, configured_form, step_data):
    """Save multistep form data to session."""
    session_key = f"multistep_form_{configured_form.pk}"
    request.session[session_key] = json.dumps(step_data, cls=DjangoJSONEncoder)


def compute_step_statuses(
    contents, step_regions, accumulated_data, current_step, *, form_class
):
    """
    Validate all steps against accumulated data to generate step statuses.

    Returns a list of dicts with keys: number, name, status, is_current.
    Status is one of: "empty", "valid", "invalid".
    """
    steps = []
    for i, region in enumerate(step_regions):
        plugins = contents[region.key]
        if not accumulated_data:
            status = "empty"
        else:
            form = create_form(
                plugins,
                form_class=form_class,
                form_kwargs={"data": accumulated_data},
            )
            has_data = any(accumulated_data.get(name) for name in form.fields)
            if not has_data:
                status = "empty"
            elif form.is_valid():
                status = "valid"
            else:
                status = "invalid"

        steps.append({
            "number": i + 1,
            "name": region.title,
            "status": status,
            "is_current": i == current_step,
        })
    return steps


def _default_get_step_regions(configured_form):
    """Return regions whose key starts with STEP_REGION_PREFIX."""
    return [
        r for r in configured_form.regions
        if r.key.startswith(STEP_REGION_PREFIX)
    ]


def _merge_post_data(accumulated_data, form):
    """Merge raw POST data into accumulated_data without validation."""
    for field_name in form.fields:
        if field_name in form.data:
            accumulated_data[field_name] = form.data[field_name]


def _render_step(
    request, configured_form, contents, step_regions, step_index, accumulated_data,
    *, renderer, form_class, validation_form_class,
):
    """Render a specific step, pre-filled with accumulated session data."""
    current_region = step_regions[step_index]
    total_steps = len(step_regions)

    form = create_form(
        contents[current_region.key],
        form_class=form_class,
        form_kwargs={"initial": {**accumulated_data, **_ref_initial(request)}},
    )

    steps = compute_step_statuses(
        contents, step_regions, accumulated_data, step_index,
        form_class=validation_form_class,
    )

    context = Context({"request": request, "form": form})
    step_content = _render_region_content(
        contents, current_region.key, context, renderer=renderer
    )

    return render(
        request,
        "feincms3_formbuilder/multistep_form.html",
        {
            "configured_form": configured_form,
            "form": form,
            "step_content": step_content,
            "current_step": step_index + 1,
            "total_steps": total_steps,
            "current_step_name": current_region.title,
            "steps": steps,
            "is_first_step": step_index == 0,
            "is_last_step": step_index == total_steps - 1,
        },
    )


def multistep_form_view(
    request, configured_form, *, renderer,
    form_class=None,
    validation_form_class=forms.Form,
    get_step_regions=None,
):
    """Handle multi-step form display and submission."""
    if form_class is None:
        form_class = configured_form.type.form_class
    if get_step_regions is None:
        get_step_regions = _default_get_step_regions
    contents = contents_for_item(configured_form, plugins=renderer.plugins())
    step_regions = get_step_regions(configured_form)

    if (total_steps := len(step_regions)) == 0:
        return render(
            request,
            "feincms3_formbuilder/form.html",
            {"configured_form": configured_form, "form": None},
        )

    step_data = get_session_data(request, configured_form)
    current_step = max(0, min(step_data["step"], total_steps - 1))
    accumulated_data = step_data["data"]
    current_region = step_regions[current_step]

    if request.method == "POST":
        form = create_form(
            contents[current_region.key],
            form_class=form_class,
            form_kwargs={"data": request.POST, "files": request.FILES},
        )

        action = request.POST.get("_action", "next")
        going_back = action == "back"
        submitting = action == "submit"

        if going_back:
            _merge_post_data(accumulated_data, form)
            step_data["step"] = max(0, current_step - 1)
            step_data["data"] = accumulated_data
            save_session_data(request, configured_form, step_data)
            return _render_step(
                request, configured_form, contents, step_regions,
                step_data["step"], accumulated_data,
                renderer=renderer, form_class=form_class,
                validation_form_class=validation_form_class,
            )

        if submitting:
            if form.is_valid():
                accumulated_data.update(form.cleaned_data)
                step_data["data"] = accumulated_data

                all_valid = True
                for region in step_regions:
                    step_form = create_form(
                        contents[region.key],
                        form_class=validation_form_class,
                        form_kwargs={"data": accumulated_data},
                    )
                    if not step_form.is_valid():
                        all_valid = False
                        break

                if all_valid:
                    # Clear session before processing
                    session_key = f"multistep_form_{configured_form.pk}"
                    request.session.pop(session_key, None)
                    return configured_form.type.process(
                        request, configured_form, accumulated_data
                    )

                save_session_data(request, configured_form, step_data)
        else:
            # next
            if form.is_valid():
                accumulated_data.update(form.cleaned_data)
                next_step = min(current_step + 1, total_steps - 1)
                step_data["step"] = next_step
                step_data["data"] = accumulated_data
                save_session_data(request, configured_form, step_data)
                return _render_step(
                    request, configured_form, contents, step_regions,
                    next_step, accumulated_data,
                    renderer=renderer, form_class=form_class,
                    validation_form_class=validation_form_class,
                )

        # Validation failed: re-render current step with errors
        steps = compute_step_statuses(
            contents, step_regions, accumulated_data, current_step,
            form_class=validation_form_class,
        )
        context = Context({"request": request, "form": form})
        step_content = _render_region_content(
            contents, current_region.key, context, renderer=renderer
        )
        return render(
            request,
            "feincms3_formbuilder/multistep_form.html",
            {
                "configured_form": configured_form,
                "form": form,
                "step_content": step_content,
                "current_step": current_step + 1,
                "total_steps": total_steps,
                "current_step_name": current_region.title,
                "steps": steps,
                "is_first_step": current_step == 0,
                "is_last_step": current_step == total_steps - 1,
            },
        )

    # GET: render current step pre-filled with session data
    return _render_step(
        request, configured_form, contents, step_regions,
        current_step, accumulated_data,
        renderer=renderer, form_class=form_class,
        validation_form_class=validation_form_class,
    )
