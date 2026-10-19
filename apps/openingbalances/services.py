from django.db import transaction

from apps.core.exceptions import BusinessRuleError
from apps.core.money import ZERO, q2
from apps.journals.services import LineInput, replace_for_source
from apps.ledgeraccounts.services import system_account

from .models import OpeningBalance, OpeningBalanceLine

SOURCE = {"source": "opening_balance", "source_model": "openingbalances.OpeningBalance"}


@transaction.atomic
def save_lines(ob: OpeningBalance, rows: list[dict]) -> OpeningBalance:
    if ob.status != OpeningBalance.Status.DRAFT:
        raise BusinessRuleError("Unpost the opening balances before changing them.")
    ob.lines.all().delete()
    seen = set()
    for row in rows:
        debit, credit = q2(row.get("debit")), q2(row.get("credit"))
        if debit == ZERO and credit == ZERO:
            continue
        if row["account"].pk in seen:
            raise BusinessRuleError(f"{row['account']} appears twice. Enter one balance per account.")
        seen.add(row["account"].pk)
        OpeningBalanceLine.objects.create(opening_balance=ob, account=row["account"], debit=debit, credit=credit)
    return ob


@transaction.atomic
def post(ob: OpeningBalance, user=None) -> OpeningBalance:
    if ob.status == OpeningBalance.Status.POSTED:
        raise BusinessRuleError("The opening balances are already posted.")
    rows = list(ob.lines.select_related("account"))
    if not rows:
        raise BusinessRuleError("Enter at least one balance first.")
    lines = [LineInput(account=r.account, debit=r.debit, credit=r.credit, description="Opening balance") for r in rows]
    difference = sum((r.debit - r.credit for r in rows), ZERO)
    if difference != ZERO:
        equity = system_account(ob.workspace, "opening_balance_equity")
        lines.append(LineInput(account=equity, debit=-difference if difference < 0 else ZERO,
                               credit=difference if difference > 0 else ZERO, description="Opening balance difference"))
    entry = replace_for_source(
        ob.workspace, **SOURCE, source_id=str(ob.pk), entry_date=ob.as_of_date,
        description=f"Opening balances at {ob.as_of_date:%d %b %Y}", lines=lines, user=user,
    )
    ob.journal, ob.status = entry, OpeningBalance.Status.POSTED
    ob.save(update_fields=["journal", "status", "updated_at"])
    return ob


@transaction.atomic
def unpost(ob: OpeningBalance, user=None) -> OpeningBalance:
    if ob.status != OpeningBalance.Status.POSTED:
        raise BusinessRuleError("The opening balances are not posted.")
    replace_for_source(ob.workspace, **SOURCE, source_id=str(ob.pk), entry_date=ob.as_of_date, description="", lines=[], user=user)
    ob.journal, ob.status = None, OpeningBalance.Status.DRAFT
    ob.save(update_fields=["journal", "status", "updated_at"])
    return ob
