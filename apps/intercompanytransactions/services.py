"""Recording a transaction between two companies of a group once, and posting both companies' entries together."""
from django.db import transaction
from django.utils import timezone

from apps.core.exceptions import BusinessRuleError
from apps.journals.services import LineInput, replace_for_source
from apps.ledgeraccounts.services import system_account

from .models import IntercompanyTransaction

K = IntercompanyTransaction.Kind
SOURCE = {"source": "intercompany", "source_model": "intercompanytransactions.IntercompanyTransaction"}
MONEY = ("cash", "bank")


def _check_accounts(kind, from_account, to_account, from_ws, to_ws):
    if from_account.workspace_id != from_ws.pk or to_account.workspace_id != to_ws.pk:
        raise BusinessRuleError("Each account must belong to its own company.")
    for account in (from_account, to_account):
        if not account.is_active:
            raise BusinessRuleError(f"{account} is inactive.")
    if kind == K.SALE:
        if from_account.account_type != "income":
            raise BusinessRuleError(f"For a sale, {from_ws.name}'s account must be an income account.")
        if to_account.account_type not in ("expense", "asset") or to_account.subtype in MONEY:
            raise BusinessRuleError(f"For a sale, {to_ws.name}'s account must be the expense (or asset) it is for.")
    elif from_account.subtype not in MONEY or to_account.subtype not in MONEY:
        raise BusinessRuleError("For a loan or a settlement, choose the bank, M-Pesa or cash accounts the money moves between.")


def _lines(t: IntercompanyTransaction):
    """(lines for the `from` company, lines for the `to` company)."""
    a, label = t.amount, f"{t.number}: {t.description}"
    due_from_f, due_to_f = system_account(t.from_workspace, "due_from_group"), system_account(t.from_workspace, "due_to_group")
    due_from_t, due_to_t = system_account(t.to_workspace, "due_from_group"), system_account(t.to_workspace, "due_to_group")
    if t.kind in (K.SALE, K.LOAN):  # `to` now owes `from`
        return ([LineInput(account=due_from_f, debit=a, description=label), LineInput(account=t.from_account, credit=a, description=label)],
                [LineInput(account=t.to_account, debit=a, description=label), LineInput(account=due_to_t, credit=a, description=label)])
    # settlement: `from` pays `to` what it owes
    return ([LineInput(account=due_to_f, debit=a, description=label), LineInput(account=t.from_account, credit=a, description=label)],
            [LineInput(account=t.to_account, debit=a, description=label), LineInput(account=due_from_t, credit=a, description=label)])


def _post(t: IntercompanyTransaction, user, *, lines=True):
    sides = _lines(t) if lines else ([], [])
    for workspace, side in ((t.from_workspace, sides[0]), (t.to_workspace, sides[1])):
        other = t.to_workspace if workspace == t.from_workspace else t.from_workspace
        replace_for_source(workspace, **SOURCE, source_id=str(t.pk), entry_date=t.transaction_date, reference=t.number,
                           description=f"{t.get_kind_display()} with {other.name}: {t.description}"[:255], lines=side, user=user,
                           dimensions=(None, None))


@transaction.atomic
def record(group, *, kind, from_workspace, to_workspace, transaction_date, description, amount, from_account, to_account, user) -> IntercompanyTransaction:
    from apps.companygroups.services import membership

    if from_workspace == to_workspace:
        raise BusinessRuleError("Choose two different companies.")
    for ws in (from_workspace, to_workspace):
        if ws.group_id != group.pk:
            raise BusinessRuleError(f"{ws.name} isn't in this group.")
        m = membership(user, ws)
        if not (m and m.has_perm("journals.post")):
            raise BusinessRuleError(f"You need to post journal entries in {ws.name} to record this.")
    if amount <= 0:
        raise BusinessRuleError("The amount must be more than zero.")
    _check_accounts(kind, from_account, to_account, from_workspace, to_workspace)
    t = IntercompanyTransaction.objects.create(
        group=group, number=f"IC-{group.transactions.count() + 1:04d}", kind=kind, from_workspace=from_workspace, to_workspace=to_workspace,
        transaction_date=transaction_date or timezone.localdate(), description=description.strip()[:255], amount=amount,
        from_account=from_account, to_account=to_account, created_by=user,
    )
    _post(t, user)  # both companies' books, in one transaction: either both post or neither does
    return t


@transaction.atomic
def void(t: IntercompanyTransaction, reason: str, user) -> IntercompanyTransaction:
    from apps.companygroups.services import membership

    if t.status == IntercompanyTransaction.Status.VOID:
        raise BusinessRuleError("This is already void.")
    if not reason.strip():
        raise BusinessRuleError("Say why it is being voided.")
    for ws in (t.from_workspace, t.to_workspace):
        m = membership(user, ws)
        if not (m and m.has_perm("journals.post")):
            raise BusinessRuleError(f"You need to post journal entries in {ws.name} to void this.")
    _post(t, user, lines=False)
    t.status, t.void_reason = IntercompanyTransaction.Status.VOID, reason.strip()[:255]
    t.save(update_fields=["status", "void_reason", "updated_at"])
    return t


def balances(group) -> list[dict]:
    """What each pair of companies owes each other from the group's transactions."""
    from collections import defaultdict
    from decimal import Decimal

    owed: dict = defaultdict(lambda: Decimal("0"))
    names = {}
    for t in group.transactions.filter(status="posted").select_related("from_workspace", "to_workspace"):
        names[t.from_workspace_id], names[t.to_workspace_id] = t.from_workspace.name, t.to_workspace.name
        # sale or loan: `to` owes `from`; settlement: `from` paid `to`, so it owes less
        if t.kind == K.SETTLEMENT:
            owed[(t.from_workspace_id, t.to_workspace_id)] -= t.amount
        else:
            owed[(t.to_workspace_id, t.from_workspace_id)] += t.amount
    rows, seen = [], set()
    for (debtor, creditor), amount in owed.items():
        if (debtor, creditor) in seen:
            continue
        seen |= {(debtor, creditor), (creditor, debtor)}
        net = amount - owed.get((creditor, debtor), Decimal("0"))
        if net == 0:
            continue
        if net < 0:
            debtor, creditor, net = creditor, debtor, -net
        rows.append({"owes": names[debtor], "to": names[creditor], "amount": net})
    return sorted(rows, key=lambda r: -r["amount"])
