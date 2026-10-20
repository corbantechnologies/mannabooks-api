from celery import shared_task
from django.utils import timezone


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def send_document_email(self, email_id: str) -> None:
    from .models import DocumentEmail
    from .services import deliver

    email = DocumentEmail.objects.select_related("workspace", "created_by").filter(pk=email_id).first()
    if email is None or email.status == DocumentEmail.Status.SENT:
        return
    try:
        deliver(email)
    except Exception as exc:  # noqa: BLE001 - recorded, retried, then shown as not sent
        email.error = str(exc)[:255]
        if self.request.retries >= self.max_retries:
            email.status = DocumentEmail.Status.FAILED
            email.save(update_fields=["status", "error", "updated_at"])
            return
        email.save(update_fields=["error", "updated_at"])
        raise self.retry(exc=exc) from exc
    email.status, email.sent_at, email.error = DocumentEmail.Status.SENT, timezone.now(), ""
    email.save(update_fields=["status", "sent_at", "error", "updated_at"])
