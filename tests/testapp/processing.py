from feincms3_formbuilder.notifications import send_form_notifications
from feincms3_formbuilder.processing import create_submission, render_success_region
from testapp.models import FormSubmission
from testapp.renderer import renderer


def process_simple_form(request, form, *, configured_form):
    data = dict(form.cleaned_data)
    submission = create_submission(
        request, configured_form, data, submission_model=FormSubmission,
    )
    send_form_notifications(
        configured_form.notifications.all(),
        context={"form_data": data, "submission": submission},
    )
    return render_success_region(request, configured_form, renderer=renderer)


def process_multistep_form(request, configured_form, accumulated_data):
    data = dict(accumulated_data)
    submission = create_submission(
        request, configured_form, data, submission_model=FormSubmission,
    )
    send_form_notifications(
        configured_form.notifications.all(),
        context={"form_data": data, "submission": submission},
    )
    return render_success_region(request, configured_form, renderer=renderer)
