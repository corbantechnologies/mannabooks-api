from datetime import timedelta

from django.conf import settings
from django.core.mail import EmailMessage
from django.utils import timezone

from apps.core.exceptions import BusinessRuleError

from .models import ReminderLog, ReminderRule

DEFAULT_RULES = [("3 days before due", -3), ("On the due date", 0), ("7 days overdue", 7), ("30 days overdue", 30)]
OPEN = ("issued", "partially_paid")


def seed_rules(workspace) -> None:
    if not ReminderRule.objects.filter(workspace=workspace).exists():
        ReminderRule.objects.bulk_create(ReminderRule(workspace=workspace, name=n, days=d) for n, d in DEFAULT_RULES)


def _fill(template: str, invoice) -> str:
    values = {
        "customer": invoice.customer.name, "number": invoice.number, "currency": invoice.currency,
        "balance": f"{invoice.balance_due:,.2f}", "total": f"{invoice.total:,.2f}",
        "due_date": invoice.due_date.strftime("%d %b %Y"), "business": invoice.workspace.name,
    }
    for key, value in values.items():
        template = template.replace("{" + key + "}", value)
    return template


def send(invoice, rule: ReminderRule | None = None, user=None) -> ReminderLog:
    if invoice.status not in OPEN:
        raise BusinessRuleError("Only unpaid issued invoices get reminders.")
    email = invoice.customer.email
    if not email:
        raise BusinessRuleError(f"{invoice.customer} has no email address. Add one to the customer first.")
    subject = _fill(rule.subject if rule else "Payment reminder: invoice {number}", invoice)[:200]
    from .models import DEFAULT_MESSAGE

    body = _fill(rule.message if rule else DEFAULT_MESSAGE, invoice)
    error = ""
    try:
        EmailMessage(subject, body, settings.DEFAULT_FROM_EMAIL, [email],
                     reply_to=[invoice.workspace.email] if invoice.workspace.email else None).send()
    except Exception as exc:  # provider down: logged and shown, the rule tries again tomorrow
        error = str(exc)[:255]
    if error and rule is not None:
        raise BusinessRuleError(error)
    return ReminderLog.objects.create(workspace=invoice.workspace, rule=rule, invoice=invoice, sent_to=email, subject=subject,
                                      error=error, created_by=user)


def run_due(today=None) -> int:
    """Send each active rule's reminders for today. A rule reminds about an invoice at most once."""
    from apps.invoices.models import Invoice

    today = today or timezone.localdate()
    sent = 0
    for rule in ReminderRule.objects.filter(is_active=True).select_related("workspace"):
        due = today - timedelta(days=rule.days)
        invoices = (Invoice.objects.filter(workspace=rule.workspace, status__in=OPEN, due_date=due)
                    .exclude(customer__email="").exclude(reminders__rule=rule).select_related("customer", "workspace"))
        for invoice in invoices:
            try:
                send(invoice, rule)
                sent += 1
            except BusinessRuleError:
                continue
    return sent
