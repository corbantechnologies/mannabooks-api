import calendar
from datetime import date, timedelta

from django.db import transaction
from django.utils import timezone

from apps.core.exceptions import BusinessRuleError

from .models import RecurringInvoice, RecurringInvoiceLine

MONTHS = {"monthly": 1, "quarterly": 3, "yearly": 12}
CATCH_UP_LIMIT = 12  # invoices one template may raise in a single run (after downtime)


def add_months(d: date, months: int, day: int) -> date:
    """`d` moved by `months`, on `day` of the month (clamped to the month's length, e.g. 31 Jan -> 28 Feb)."""
    month_index = d.month - 1 + months
    year, month = d.year + month_index // 12, month_index % 12 + 1
    return date(year, month, min(day, calendar.monthrange(year, month)[1]))


def following(template: RecurringInvoice, run_date: date) -> date:
    if template.frequency == RecurringInvoice.Frequency.WEEKLY:
        return run_date + timedelta(days=7)
    return add_months(run_date, MONTHS[template.frequency], template.start_date.day)


@transaction.atomic
def save(workspace, *, data: dict, rows: list[dict] | None, user=None, template: RecurringInvoice | None = None) -> RecurringInvoice:
    if template is None:
        template = RecurringInvoice(workspace=workspace, created_by=user)
    start_changed = "start_date" in data and data["start_date"] != template.start_date
    for key, value in data.items():
        setattr(template, key, value)
    if template.customer_id is None:
        raise BusinessRuleError("Choose a customer.")
    if start_changed or template.pk is None:
        template.next_run_date = max(template.start_date, timezone.localdate()) if template.pk else template.start_date
    if template.end_date and template.end_date < template.start_date:
        raise BusinessRuleError("The end date can't be before the start date.")
    template.save()
    if rows is not None:
        if not rows:
            raise BusinessRuleError("Add at least one line.")
        template.lines.all().delete()
        RecurringInvoiceLine.objects.bulk_create(
            RecurringInvoiceLine(recurring_invoice=template, line_no=n, product=r.get("product"), description=r.get("description", ""),
                                 quantity=r.get("quantity") or 1, unit_price=r.get("unit_price"), discount_percent=r.get("discount_percent") or 0,
                                 tax_rate=r.get("tax_rate"))
            for n, r in enumerate(rows, start=1)
        )
    return template


def _rows(template):
    rows = []
    for line in template.lines.select_related("product", "tax_rate"):
        row = {"product": line.product, "description": line.description, "quantity": line.quantity, "discount_percent": line.discount_percent}
        if line.unit_price is not None:
            row["unit_price"] = line.unit_price
        if line.tax_rate is not None:
            row["tax_rate"] = line.tax_rate
        rows.append(row)
    return rows


@transaction.atomic
def raise_invoice(template: RecurringInvoice, run_date: date, user=None):
    """Raise one invoice for `run_date` and move the schedule on."""
    from apps.invoices import services as invoices

    invoice = invoices.save_draft(
        template.workspace, user=user or template.created_by, rows=_rows(template),
        header={"customer": template.customer, "issue_date": run_date, "prices_include_tax": template.prices_include_tax,
                "reference": template.reference, "notes": template.notes},
    )
    if template.auto_issue:
        invoices.issue(invoice, user or template.created_by)
    template.invoices_created += 1
    template.last_invoice = invoice
    template.last_error = ""
    template.next_run_date = following(template, run_date)
    if template.end_date and template.next_run_date > template.end_date:
        template.status = RecurringInvoice.Status.ENDED
    template.save()
    return invoice


def run_template(template: RecurringInvoice, today: date | None = None) -> list:
    """Raise every invoice that is due (catching up after downtime, up to a limit)."""
    today = today or timezone.localdate()
    created = []
    while (template.status == RecurringInvoice.Status.ACTIVE and template.next_run_date <= today
           and len(created) < CATCH_UP_LIMIT):
        try:
            created.append(raise_invoice(template, template.next_run_date))
        except BusinessRuleError as exc:  # e.g. a closed period or an inactive customer: keep it visible
            RecurringInvoice.objects.filter(pk=template.pk).update(last_error=str(exc)[:255])
            break
        template.refresh_from_db()
    return created


def run_due(today: date | None = None) -> int:
    today = today or timezone.localdate()
    count = 0
    for template in RecurringInvoice.objects.filter(status=RecurringInvoice.Status.ACTIVE, next_run_date__lte=today):
        count += len(run_template(template, today))
    return count
