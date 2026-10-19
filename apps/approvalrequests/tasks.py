from celery import shared_task
from django.conf import settings
from django.core.mail import send_mail


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def send_approval_email(self, subject: str, body: str, emails: list[str]) -> None:
    try:
        send_mail(subject, body, settings.DEFAULT_FROM_EMAIL, emails)
    except Exception as exc:  # noqa: BLE001 - retry on any mail failure
        raise self.retry(exc=exc) from exc
