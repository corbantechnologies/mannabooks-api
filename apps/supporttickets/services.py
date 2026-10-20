from django.db import transaction
from django.utils import timezone

from apps.core.exceptions import BusinessRuleError

from .models import SupportTicket

S = SupportTicket.Status


def _message(user, body: str, *, staff: bool, internal: bool = False) -> dict:
    return {"author_id": str(user.pk), "author_name": user.full_name, "staff": staff, "internal": internal, "body": body.strip(),
            "at": timezone.now().isoformat()}


@transaction.atomic
def open_ticket(user, *, workspace, category: str, subject: str, body: str, page: str = "") -> SupportTicket:
    if not body.strip():
        raise BusinessRuleError("Tell us what happened or what you need.")
    number = f"T-{SupportTicket.objects.count() + 1001}"
    return SupportTicket.objects.create(number=number, workspace=workspace, raised_by=user, category=category, subject=subject.strip()[:200],
                                        page=page[:255], messages=[_message(user, body, staff=False)])


def reply(ticket: SupportTicket, user, body: str, *, staff: bool, internal: bool = False) -> SupportTicket:
    if not body.strip():
        raise BusinessRuleError("Write a reply.")
    if ticket.status == S.CLOSED and not staff:
        raise BusinessRuleError("This ticket is closed. Open a new one.")
    ticket.messages = [*ticket.messages, _message(user, body, staff=staff, internal=internal)]
    if not internal:
        ticket.last_reply_by_staff = staff
        if staff and ticket.status == S.OPEN:
            ticket.status = S.WAITING
        elif not staff and ticket.status in (S.WAITING, S.RESOLVED):
            ticket.status, ticket.resolved_at = S.OPEN, None  # the customer answered or came back
    ticket.save()
    if staff and not internal:
        _email_customer(ticket, body)
    return ticket


def _email_customer(ticket: SupportTicket, body: str) -> None:
    from django.conf import settings
    from django.core.mail import send_mail

    def send():
        send_mail(f"[{ticket.number}] {ticket.subject}", f"{body}\n\nReply in MannaBooks: Help and feedback.\n\nMannaBooks support",
                  settings.DEFAULT_FROM_EMAIL, [ticket.raised_by.email], fail_silently=True)

    transaction.on_commit(send)


def visible_to(user, staff: bool):
    """The customer's own tickets; for staff, every ticket. Internal notes are stripped for customers."""
    qs = SupportTicket.objects.select_related("workspace", "raised_by", "assigned_to")
    return qs if staff else qs.filter(raised_by=user)


def public_messages(ticket: SupportTicket, staff: bool) -> list[dict]:
    return [m for m in ticket.messages if staff or not m.get("internal")]
