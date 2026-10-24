import logging

from celery import shared_task
from django.conf import settings
from django.core.mail import send_mail


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def send_catalogue_email(self, subject: str, body: str, emails: list[str]) -> None:
    try:
        send_mail(subject, body, settings.DEFAULT_FROM_EMAIL, emails)
    except Exception as exc:  # noqa: BLE001 - retry on any mail failure
        raise self.retry(exc=exc) from exc


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def send_catalogue_link(self, catalogue_id: str, to: list[str], message: str, reply_to: list[str]) -> None:
    from email.utils import formataddr, parseaddr
    from html import escape

    from django.core.mail import EmailMultiAlternatives

    from .models import Catalogue

    c = Catalogue.objects.select_related("workspace").get(pk=catalogue_id)
    business = c.workspace.legal_name or c.workspace.name
    text = f"{message}\n\nOpen the catalogue: {c.url}\n\n{business}\nSent with MannaBooks"
    html = ("<div style='font-family:Arial,sans-serif;font-size:14px;color:#1c1917;max-width:600px'>"
            + "".join(f"<p style='margin:0 0 10px'>{escape(p)}</p>" for p in message.split("\n") if p.strip())
            + f"<p style='margin:20px 0'><a href='{escape(c.url)}' style='background:#065f46;color:#fff;padding:10px 16px;border-radius:6px;"
              "text-decoration:none'>Open the catalogue</a></p>"
            + f"<p style='margin:24px 0 0;color:#57534e'>{escape(business)}</p>"
            + "<p style='margin:4px 0 0;color:#a8a29e;font-size:12px'>Sent with MannaBooks</p></div>")
    sender = parseaddr(settings.DEFAULT_FROM_EMAIL)[1] or "no-reply@mannabooks.co.ke"
    msg = EmailMultiAlternatives(f"{c.name} from {business}", text, formataddr((f"{c.workspace.name} via MannaBooks", sender)), to, reply_to=reply_to)
    msg.attach_alternative(html, "text/html")
    from apps.documentemails import pdfs

    if pdfs.enabled():  # the catalogue as a PDF too; if it can't be made, the email still goes with the link
        from . import services

        try:
            msg.attach(services.pdf_filename(c), services.pdf(c), "application/pdf")
        except Exception:  # noqa: BLE001
            logging.getLogger("mannabooks.pdf").exception("Catalogue PDF for %s failed", c.pk)
    try:
        msg.send()
    except Exception as exc:  # noqa: BLE001 - retry on any mail failure
        raise self.retry(exc=exc) from exc
