"""Compose and send a document by email. The email carries a summary, the lines, how to pay and, for invoices,
the private link to view and pay online. (PDF attachments come with the PDF service.)"""
from email.utils import formataddr, parseaddr
from html import escape

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.core.exceptions import BusinessRuleError

from .models import DocumentEmail
from .registry import DOCS


def _money(value) -> str:
    return f"{value:,.2f}"


def defaults(workspace, doc_type: str, document) -> dict:
    spec = DOCS[doc_type]
    party = spec.party(document)
    title = spec.title(document)
    business = workspace.legal_name or workspace.name
    total = f"{getattr(document, 'currency', '') or workspace.currency} {_money(document.total)}".strip()
    if doc_type == "invoice":
        note = f"Please find {title.lower()} {document.number} for {total}, due {document.due_date:%d %b %Y}."
    elif doc_type == "quotation":
        note = f"Thank you for your enquiry. Please find our quotation {document.number} for {total}."
    elif doc_type == "purchase_order":
        note = f"Please supply the items on purchase order {document.number} ({total})."
    else:
        note = f"Please find {title.lower()} {document.number} for {total}."
    return {
        "to": getattr(party, "email", "") or "",
        "cc": "",
        "subject": f"{title} {document.number} from {business}",
        "message": f"Dear {getattr(party, 'name', '') or 'customer'},\n\n{note}\n\nKind regards,\n{business}",
    }


def _addresses(text: str) -> list[str]:
    out = []
    for part in text.replace(";", ",").split(","):
        address = parseaddr(part.strip())[1]
        if address:
            if "@" not in address or "." not in address.split("@")[-1]:
                raise BusinessRuleError(f"{part.strip()} isn't an email address.")
            out.append(address)
    return out


def _link(workspace, doc_type: str, document) -> str:
    if doc_type != "invoice" or document.balance_due <= 0:
        return ""
    from apps.portallinks.models import PortalLink

    now = timezone.now()
    link = (PortalLink.objects.filter(workspace=workspace, invoice=document, revoked_at__isnull=True)
            .exclude(expires_at__lt=now).order_by("-created_at").first())
    if link is None:
        link = PortalLink.objects.create(workspace=workspace, customer=document.customer, invoice=document)
    return link.url


def _body(workspace, doc_type: str, document, message: str, link: str) -> tuple[str, str]:
    """Plain text and HTML versions."""
    from apps.paymentoptions.models import PaymentOption

    spec = DOCS[doc_type]
    currency = getattr(document, "currency", "") or workspace.currency
    lines = list(document.lines.all())
    pay = [o.lines() for o in PaymentOption.objects.filter(workspace=workspace, show_on_documents=True)] if doc_type in ("invoice", "quotation") else []
    pay = [[line.replace("the document number", document.number) for line in o] for o in pay]
    business = workspace.legal_name or workspace.name
    contact = " · ".join(x for x in [workspace.phone, workspace.email] if x)

    text = [message, "", f"{spec.title(document)} {document.number} ({spec.date(document):%d %b %Y})", ""]
    text += [f"- {line.description}: {line.quantity.normalize():f} x {_money(getattr(line, 'unit_price', None) or getattr(line, 'unit_cost', 0))}"
             f" = {_money(line.total_amount)}" for line in lines]
    text += ["", f"Total {currency} {_money(document.total)}"]
    if doc_type == "invoice":
        text.append(f"Balance due {currency} {_money(document.balance_due)} by {document.due_date:%d %b %Y}")
    if link:
        text += ["", f"View and pay online: {link}"]
    if pay:
        text += ["", "How to pay:"] + ["  " + " | ".join(o) for o in pay]
    text += ["", f"{business}" + (f" · {contact}" if contact else ""), "Sent with MannaBooks"]

    rows = "".join(
        f"<tr><td style='padding:6px 8px;border-bottom:1px solid #e7e5e4'>{escape(line.description)}</td>"
        f"<td style='padding:6px 8px;border-bottom:1px solid #e7e5e4;text-align:right'>{line.quantity.normalize():f}</td>"
        f"<td style='padding:6px 8px;border-bottom:1px solid #e7e5e4;text-align:right'>{_money(line.total_amount)}</td></tr>" for line in lines)
    html = (
        "<div style='font-family:Arial,sans-serif;font-size:14px;color:#1c1917;max-width:600px'>"
        + "".join(f"<p style='margin:0 0 10px'>{escape(p)}</p>" for p in message.split("\n") if p.strip())
        + f"<h2 style='font-size:16px;margin:20px 0 6px'>{escape(spec.title(document))} {escape(document.number)}</h2>"
        + f"<p style='margin:0 0 8px;color:#57534e'>{spec.date(document):%d %b %Y}</p>"
        + "<table style='border-collapse:collapse;width:100%'><tr style='color:#78716c;font-size:12px;text-align:left'><th style='padding:6px 8px'>Item</th>"
        + "<th style='padding:6px 8px;text-align:right'>Qty</th><th style='padding:6px 8px;text-align:right'>Amount</th></tr>"
        + rows + "</table>"
        + f"<p style='font-weight:bold;text-align:right;margin:10px 8px'>Total {escape(currency)} {_money(document.total)}</p>"
        + (f"<p style='text-align:right;margin:0 8px'>Balance due {escape(currency)} {_money(document.balance_due)} by {document.due_date:%d %b %Y}</p>"
           if doc_type == "invoice" else "")
        + (f"<p style='margin:20px 0'><a href='{escape(link)}' style='background:#065f46;color:#fff;padding:10px 16px;border-radius:6px;"
           f"text-decoration:none'>View and pay online</a></p>" if link else "")
        + ("<p style='margin:16px 0 4px;font-weight:bold'>How to pay</p>" + "".join(f"<p style='margin:0 0 6px'>{'<br>'.join(escape(x) for x in o)}</p>" for o in pay)
           if pay else "")
        + f"<p style='margin:24px 0 0;color:#57534e'>{escape(business)}" + (f" · {escape(contact)}" if contact else "") + "</p>"
        + "<p style='margin:4px 0 0;color:#a8a29e;font-size:12px'>Sent with MannaBooks</p></div>"
    )
    return "\n".join(text), html


@transaction.atomic
def send(workspace, *, doc_type: str, document, to: str, cc: str = "", subject: str, message: str, user) -> DocumentEmail:
    if not getattr(document, "number", ""):
        raise BusinessRuleError("Save and number the document before sending it.")
    if getattr(document, "status", "") in ("draft",) and doc_type in ("invoice", "purchase_order"):
        raise BusinessRuleError("Issue or approve the document before sending it.")
    if getattr(document, "status", "") == "void":
        raise BusinessRuleError("This document is void.")
    recipients, copies = _addresses(to), _addresses(cc)
    if not recipients:
        raise BusinessRuleError("Enter who to send it to.")
    link = _link(workspace, doc_type, document)
    email = DocumentEmail.objects.create(workspace=workspace, created_by=user, document_type=doc_type, object_id=document.pk,
                                         document_number=document.number, to=", ".join(recipients), cc=", ".join(copies),
                                         subject=subject.strip()[:200], message=message, link=link)
    if doc_type == "quotation" and document.status == "draft":
        document.status = "sent"
        document.save(update_fields=["status", "updated_at"])
    from .tasks import send_document_email

    transaction.on_commit(lambda: send_document_email.delay(str(email.pk)))
    return email


def deliver(email: DocumentEmail) -> None:
    """Called by the worker: build the message and hand it to the mail service."""
    from django.core.mail import EmailMultiAlternatives

    spec = DOCS[email.document_type]
    document = spec.get(email.workspace, email.object_id)
    workspace = email.workspace
    text, html = _body(workspace, email.document_type, document, email.message, email.link)
    sender = parseaddr(settings.DEFAULT_FROM_EMAIL)[1] or "no-reply@mannabooks.co.ke"
    reply_to = [x for x in [workspace.email, getattr(email.created_by, "email", "")] if x][:1]
    msg = EmailMultiAlternatives(email.subject, text, formataddr((f"{workspace.name} via MannaBooks", sender)),
                                 [x.strip() for x in email.to.split(",") if x.strip()], cc=[x.strip() for x in email.cc.split(",") if x.strip()],
                                 reply_to=reply_to)
    msg.attach_alternative(html, "text/html")
    msg.send()
