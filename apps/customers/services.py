from decimal import Decimal

from django.db.models import DecimalField, OuterRef, Subquery, Sum, Value
from django.db.models.functions import Coalesce

from apps.core.money import ZERO

OPEN_INVOICES = ["issued", "partially_paid"]


def _sum(model, field, **filters):
    qs = model.objects.filter(customer=OuterRef("pk"), **filters).values("customer").annotate(s=Sum(field)).values("s")
    return Coalesce(Subquery(qs, output_field=DecimalField(max_digits=18, decimal_places=2)), Value(ZERO))


def with_balance(queryset):
    """Annotate `balance`: open invoices less money and credits not yet applied to an invoice."""
    from apps.creditnotes.models import CreditNote
    from apps.invoices.models import Invoice
    from apps.payments.models import Payment

    return queryset.annotate(
        open_invoices=_sum(Invoice, "balance_due", status__in=OPEN_INVOICES),
        unallocated_payments=_sum(Payment, "unallocated_amount", status="posted"),
        unapplied_credits=_sum(CreditNote, "unapplied_amount", status="issued"),
    )


def balance_of(customer) -> Decimal:
    from apps.customers.models import Customer

    c = with_balance(Customer.objects.filter(pk=customer.pk)).get()
    return c.open_invoices - c.unallocated_payments - c.unapplied_credits


def statement(customer, start=None, end=None) -> dict:
    """Invoices, payments and credit notes in date order, with a running balance."""
    from apps.creditnotes.models import CreditNote
    from apps.invoices.models import Invoice
    from apps.payments.models import Payment

    events = []
    for inv in Invoice.objects.filter(customer=customer).exclude(status__in=["draft", "void"]):
        events.append((inv.issue_date, inv.created_at, inv.kind, inv.number, inv.id, inv.total, ZERO))
    for pay in Payment.objects.filter(customer=customer, status="posted"):
        events.append((pay.payment_date, pay.created_at, "payment", pay.number, pay.id, ZERO, pay.amount))
    for cn in CreditNote.objects.filter(customer=customer, status="issued"):
        events.append((cn.issue_date, cn.created_at, "credit_note", cn.number, cn.id, ZERO, cn.total))
    events.sort(key=lambda e: (e[0], e[1]))
    opening, running, rows = ZERO, ZERO, []
    for date, _, kind, number, pk, debit, credit in events:
        if start and date < start:
            opening += debit - credit
            continue
        if end and date > end:
            continue
        if not rows:
            running = opening
        running += debit - credit
        rows.append({"date": date, "kind": kind, "number": number, "document_id": pk, "debit": debit,
                     "credit": credit, "balance": running})
    return {"opening_balance": opening, "rows": rows, "closing_balance": rows[-1]["balance"] if rows else opening}
