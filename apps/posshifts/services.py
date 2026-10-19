from decimal import Decimal

from django.db import IntegrityError, transaction
from django.db.models import Count, Sum
from django.utils import timezone

from apps.core.exceptions import BusinessRuleError
from apps.core.money import ZERO, q2
from apps.journals.services import LineInput, replace_for_source
from apps.sequences.services import next_value

from .models import PosShift

SOURCE = {"source": "pos_shift", "source_model": "posshifts.PosShift"}


def open_shift(register, user, opening_float) -> PosShift:
    if not register.is_active:
        raise BusinessRuleError("This till is inactive.")
    if PosShift.objects.filter(register=register, status=PosShift.Status.OPEN).exists():
        raise BusinessRuleError("This till already has an open shift. Close it first.")
    if PosShift.objects.filter(workspace=register.workspace, cashier=user, status=PosShift.Status.OPEN).exists():
        raise BusinessRuleError("You already have an open shift on another till.")
    try:
        with transaction.atomic():
            return PosShift.objects.create(workspace=register.workspace, register=register, cashier=user, created_by=user,
                                           number=next_value(register.workspace, "pos_shift"), opening_float=q2(opening_float or 0))
    except IntegrityError as exc:  # two people opened at the same moment
        raise BusinessRuleError("This till already has an open shift.") from exc


def summary(shift: PosShift) -> dict:
    """Takings by payment method, from the shift's issued cash sales."""
    rows = (shift.receipts.filter(status="issued").values("method").annotate(count=Count("id"), total=Sum("total")).order_by("method"))
    by_method = {r["method"]: {"count": r["count"], "total": r["total"] or ZERO} for r in rows}
    cash = by_method.get("cash", {}).get("total", ZERO)
    return {
        "by_method": [{"method": m, "count": v["count"], "total": str(v["total"])} for m, v in by_method.items()],
        "sales_count": sum(v["count"] for v in by_method.values()),
        "sales_total": str(sum((v["total"] for v in by_method.values()), ZERO)),
        "expected_cash": str(shift.opening_float + cash),
        "voided_count": shift.receipts.filter(status="void").count(),
    }


@transaction.atomic
def close_shift(shift: PosShift, counted_cash, notes: str = "", user=None) -> PosShift:
    """Count the drawer. A difference is posted to Cash over and short, so the cash account matches the drawer."""
    from apps.ledgeraccounts.models import LedgerAccount
    from apps.ledgeraccounts.services import seed_chart, system_account

    shift = PosShift.objects.select_for_update().get(pk=shift.pk)
    if shift.status != PosShift.Status.OPEN:
        raise BusinessRuleError("This shift is already closed.")
    counted = q2(counted_cash)
    if counted < 0:
        raise BusinessRuleError("The counted cash can't be negative.")
    shift.expected_cash = Decimal(summary(shift)["expected_cash"])
    shift.counted_cash, shift.cash_difference = counted, counted - shift.expected_cash
    shift.status, shift.closed_at, shift.closing_notes = PosShift.Status.CLOSED, timezone.now(), notes
    shift.save()
    if shift.cash_difference:
        if not LedgerAccount.objects.filter(workspace=shift.workspace, system_key="cash_short").exists():
            seed_chart(shift.workspace)  # workspaces created before this account existed
        cash, over_short, diff = shift.register.account_for("cash"), system_account(shift.workspace, "cash_short"), abs(shift.cash_difference)
        label = f"Shift {shift.number} cash {'over' if shift.cash_difference > 0 else 'short'}"
        lines = ([LineInput(account=cash, debit=diff, description=label), LineInput(account=over_short, credit=diff, description=label)]
                 if shift.cash_difference > 0 else
                 [LineInput(account=over_short, debit=diff, description=label), LineInput(account=cash, credit=diff, description=label)])
        replace_for_source(shift.workspace, **SOURCE, source_id=str(shift.pk), entry_date=timezone.localdate(), reference=shift.number,
                           description=label, lines=lines, user=user)
    return shift
