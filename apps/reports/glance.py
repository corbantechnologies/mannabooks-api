"""
The business at a glance: what needs attention now. Sales this month against last, quotes waiting, money owed and coming
due on both sides, and cash. Each part is there only for someone allowed to see it, and follows their department limit.
"""
from datetime import timedelta

from django.db.models import Count, F, Sum
from django.utils import timezone

from apps.core.money import ZERO
from apps.core.scoping import limited_department, scope_queryset

SOON_DAYS, LIST = 7, 6


def _sum(qs, field, rate=True):
    return qs.aggregate(t=Sum(F(field) * F("exchange_rate") if rate else F(field)))["t"] or ZERO


def _month_start(day):
    return day.replace(day=1)


def glance(request) -> dict:
    ws, m = request.workspace, request.membership
    today = timezone.localdate()
    can = m.has_perm
    out = {"today": today, "sales": None, "quotes": None, "receivables": None, "payables": None, "cash": None}

    if can("invoices.view") or can("receipts.view"):
        out["sales"] = _sales(request, today)
    if can("quotations.view"):
        out["quotes"] = _quotes(request, today)
    if can("invoices.view"):
        out["receivables"] = _receivables(request, today)
    if can("bills.view"):
        out["payables"] = _payables(request, today, can("paymentvouchers.view"))
    if can("banking.view") and limited_department(request) is None:
        out["cash"] = _cash(ws)
    return out


def _sales(request, today) -> dict:
    """Sales before VAT (invoices, debit notes and cash sales), this month so far against the same days last month."""
    from apps.invoices.models import Invoice
    from apps.payments.models import Payment
    from apps.receipts.models import Receipt

    ws = request.workspace
    this_start = _month_start(today)
    last_start = _month_start(this_start - timedelta(days=1))
    last_same_day = min(last_start + timedelta(days=today.day - 1), this_start - timedelta(days=1))
    invoices = scope_queryset(Invoice.objects.filter(workspace=ws).exclude(status__in=["draft", "void"]), request)
    receipts = scope_queryset(Receipt.objects.filter(workspace=ws, status="issued"), request)

    def sold(start, end):
        return (_sum(invoices.filter(issue_date__gte=start, issue_date__lte=end), "subtotal")
                + _sum(receipts.filter(issue_date__gte=start, issue_date__lte=end), "subtotal"))

    this_month, last_to_date = sold(this_start, today), sold(last_start, last_same_day)
    last_month = sold(last_start, this_start - timedelta(days=1))
    collected = None
    if request.membership.has_perm("payments.view"):
        paid = scope_queryset(Payment.objects.filter(workspace=ws, payment_date__gte=this_start, payment_date__lte=today).exclude(status="void"), request)
        collected = _sum(paid, "amount", rate=False) + _sum(receipts.filter(issue_date__gte=this_start, issue_date__lte=today), "total")
    return {
        "this_month": this_month, "last_month": last_month, "last_month_to_date": last_to_date,
        "change_percent": round(float((this_month - last_to_date) / last_to_date * 100), 1) if last_to_date else None,
        "collected": collected, "month_label": today.strftime("%B"), "last_month_label": last_start.strftime("%B"),
    }


def _quotes(request, today) -> dict:
    from apps.quotations.models import Quotation

    qs = scope_queryset(Quotation.objects.filter(workspace=request.workspace), request)
    open_ = qs.filter(status__in=["draft", "sent"], valid_until__gte=today)
    accepted = qs.filter(status="accepted")
    expiring = open_.filter(status="sent", valid_until__lte=today + timedelta(days=SOON_DAYS))
    to_review = qs.filter(status="draft", catalogue__isnull=False)
    return {
        "open_count": open_.count(), "open_value": _sum(open_, "total"),
        "sent_count": open_.filter(status="sent").count(), "draft_count": open_.filter(status="draft").count(),
        "to_review_count": to_review.count(),
        "expiring_count": expiring.count(), "expiring_value": _sum(expiring, "total"),
        "accepted_count": accepted.count(), "accepted_value": _sum(accepted, "total"),
        "list": [_doc(q, q.customer.name, q.valid_until, q.total, today, "quotations") for q in
                 accepted.select_related("customer").order_by("valid_until")[:LIST]],
    }


def _receivables(request, today) -> dict:
    from apps.invoices.models import Invoice

    qs = scope_queryset(Invoice.objects.filter(workspace=request.workspace), request)
    unpaid = qs.filter(status__in=["issued", "partially_paid"], balance_due__gt=0)
    overdue = unpaid.filter(due_date__lt=today)
    soon = unpaid.filter(due_date__gte=today, due_date__lte=today + timedelta(days=SOON_DAYS))
    debtors = (overdue.values("customer__name").annotate(amount=Sum(F("balance_due") * F("exchange_rate")), n=Count("id"))
               .order_by("-amount")[:5])
    return {
        "total": _sum(unpaid, "balance_due"), "count": unpaid.count(),
        "overdue": _sum(overdue, "balance_due"), "overdue_count": overdue.count(),
        "due_soon": _sum(soon, "balance_due"), "due_soon_count": soon.count(),
        "draft_count": qs.filter(status="draft").count(),
        "list": [_doc(i, i.customer.name, i.due_date, i.balance_due, today, "invoices") for i in
                 unpaid.filter(due_date__lte=today + timedelta(days=SOON_DAYS)).select_related("customer").order_by("due_date")[:LIST]],
        "top_overdue": [{"name": d["customer__name"], "amount": d["amount"] or ZERO, "count": d["n"]} for d in debtors],
    }


def _payables(request, today, see_vouchers) -> dict:
    from apps.bills.models import Bill
    from apps.paymentvouchers.models import PaymentVoucher

    # bills are in the base currency
    qs = scope_queryset(Bill.objects.filter(workspace=request.workspace), request)
    unpaid = qs.filter(status__in=["posted", "partially_paid"], balance_due__gt=0)
    overdue = unpaid.filter(due_date__lt=today)
    soon = unpaid.filter(due_date__gte=today, due_date__lte=today + timedelta(days=SOON_DAYS))
    vouchers = scope_queryset(PaymentVoucher.objects.filter(workspace=request.workspace, status="draft"), request) if see_vouchers else None
    return {
        "total": _sum(unpaid, "balance_due", rate=False), "count": unpaid.count(),
        "overdue": _sum(overdue, "balance_due", rate=False), "overdue_count": overdue.count(),
        "due_soon": _sum(soon, "balance_due", rate=False), "due_soon_count": soon.count(),
        "draft_count": qs.filter(status="draft").count(),
        "vouchers_waiting": vouchers.count() if vouchers is not None else None,
        "vouchers_waiting_value": vouchers.aggregate(t=Sum("total"))["t"] or ZERO if vouchers is not None else None,
        "list": [_doc(b, b.supplier.name, b.due_date, b.balance_due, today, "bills", b.supplier_invoice_number) for b in
                 unpaid.filter(due_date__lte=today + timedelta(days=SOON_DAYS)).select_related("supplier").order_by("due_date")[:LIST]],
    }


def _cash(ws) -> dict:
    from apps.journals.models import JournalLine

    lines = JournalLine.objects.filter(entry__workspace=ws, account__subtype__in=["cash", "bank"]).exclude(entry__status="draft")
    by_account = (lines.values("account_id", "account__name").annotate(d=Sum("debit"), c=Sum("credit")).order_by("account__name"))
    accounts = [{"name": r["account__name"], "balance": (r["d"] or ZERO) - (r["c"] or ZERO)} for r in by_account]
    return {"total": sum((a["balance"] for a in accounts), ZERO), "accounts": accounts}


def _doc(doc, party, due, amount, today, kind, their_number="") -> dict:
    return {"id": str(doc.pk), "kind": kind, "number": doc.number or their_number, "party": party, "date": due,
            "days": (due - today).days, "amount": amount, "currency": getattr(doc, "currency", "") or doc.workspace.currency}
