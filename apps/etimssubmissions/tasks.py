from celery import shared_task
from django.conf import settings

MAX_ATTEMPTS = 5


@shared_task(bind=True, max_retries=MAX_ATTEMPTS, default_retry_delay=120)
def send_submission(self, submission_id: str) -> None:
    from apps.etimsdevices.models import EtimsDevice

    from .client import EtimsError, save_sale
    from .models import EtimsSubmission
    from .services import apply_result

    if not settings.ETIMS_ENABLED:
        return
    submission = EtimsSubmission.objects.filter(pk=submission_id).first()
    if submission is None or submission.status == EtimsSubmission.Status.SIGNED:
        return
    device = EtimsDevice.objects.filter(workspace=submission.workspace, is_active=True).first()
    submission.attempts += 1
    try:
        if device is None:
            raise EtimsError("The eTIMS device is no longer active.")
        apply_result(submission, save_sale(device, submission.payload))
    except EtimsError as exc:
        submission.last_error = str(exc)
        final = submission.attempts >= MAX_ATTEMPTS
        if final:
            submission.status = EtimsSubmission.Status.FAILED
            _mark_failed(submission)
        submission.save(update_fields=["attempts", "last_error", "status", "updated_at"])
        if not final:
            raise self.retry(exc=exc) from exc


def _mark_failed(submission) -> None:
    from apps.creditnotes.models import CreditNote
    from apps.invoices.models import Invoice
    from apps.receipts.models import Receipt

    model = {"invoice": Invoice, "receipt": Receipt, "credit_note": CreditNote}[submission.document_type]
    model.objects.filter(pk=submission.document_id).update(etims_status="failed")
