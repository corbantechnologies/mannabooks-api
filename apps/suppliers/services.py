from decimal import Decimal

from django.db.models import DecimalField, OuterRef, Subquery, Sum, Value
from django.db.models.functions import Coalesce

from apps.core.money import ZERO

OPEN_BILLS = ["posted", "partially_paid"]


def _sum(model, field, **filters):
    qs = model.objects.filter(supplier=OuterRef("pk"), **filters).values("supplier").annotate(s=Sum(field)).values("s")
    return Coalesce(Subquery(qs, output_field=DecimalField(max_digits=18, decimal_places=2)), Value(ZERO))


def with_balance(queryset):
    """Annotate `balance`: what the business owes the supplier (open bills less unapplied payments)."""
    from apps.bills.models import Bill
    from apps.supplierpayments.models import SupplierPayment

    return queryset.annotate(
        open_bills=_sum(Bill, "balance_due", status__in=OPEN_BILLS),
        unallocated_payments=_sum(SupplierPayment, "unallocated_amount", status="posted"),
    )


def balance_of(supplier) -> Decimal:
    from .models import Supplier

    s = with_balance(Supplier.objects.filter(pk=supplier.pk)).get()
    return s.open_bills - s.unallocated_payments


def statement(supplier, start=None, end=None) -> dict:
    """Bills and payments in date order, with a running balance owed."""
    from apps.bills.models import Bill
    from apps.supplierpayments.models import SupplierPayment

    events = [(b.bill_date, b.created_at, "bill", b.number, b.id, b.total, ZERO, b.supplier_invoice_number)
              for b in Bill.objects.filter(supplier=supplier).exclude(status__in=["draft", "void"])]
    events += [(p.payment_date, p.created_at, "payment", p.number, p.id, ZERO, p.amount + p.withholding_amount, p.reference)
               for p in SupplierPayment.objects.filter(supplier=supplier, status="posted")]
    events.sort(key=lambda e: (e[0], e[1]))
    opening, running, rows = ZERO, ZERO, []
    for date, _, kind, number, pk, billed, paid, ref in events:
        if start and date < start:
            opening += billed - paid
            continue
        if end and date > end:
            continue
        if not rows:
            running = opening
        running += billed - paid
        rows.append({"date": date, "kind": kind, "number": number, "document_id": pk, "reference": ref or "",
                     "billed": billed, "paid": paid, "balance": running})
    return {"opening_balance": opening, "rows": rows, "closing_balance": rows[-1]["balance"] if rows else opening}
