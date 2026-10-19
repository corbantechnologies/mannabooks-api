from decimal import Decimal

from django.db import transaction
from django.db.models import Sum

from apps.core.money import ZERO
from apps.ledgeraccounts.models import LedgerAccount

from .models import BankAccount

KIND_OF = {"cash": "cash", "mpesa": "mobile"}


def sync(workspace) -> None:
    """Every active cash or bank ledger account gets a bank account record (workspaces from before banking existed)."""
    have = set(BankAccount.objects.filter(workspace=workspace).values_list("ledger_account_id", flat=True))
    BankAccount.objects.bulk_create(
        BankAccount(workspace=workspace, name=a.name, ledger_account=a,
                    kind="cash" if a.subtype == "cash" else KIND_OF.get(a.system_key, "bank"))
        for a in LedgerAccount.objects.filter(workspace=workspace, subtype__in=["cash", "bank"]).exclude(pk__in=have)
    )


@transaction.atomic
def create(workspace, *, name, kind, user=None, **details) -> BankAccount:
    """A new bank account with its own ledger account (11xx for banks and mobile money, 10xx for cash)."""
    subtype, prefix = ("cash", "10") if kind == "cash" else ("bank", "11")
    codes = [int(c) for c in LedgerAccount.objects.filter(workspace=workspace, code__startswith=prefix).values_list("code", flat=True) if c.isdigit()]
    code = str(max(codes, default=int(prefix) * 100) + 10)
    ledger = LedgerAccount.objects.create(workspace=workspace, code=code, name=name, account_type="asset", subtype=subtype, created_by=user)
    return BankAccount.objects.create(workspace=workspace, name=name, kind=kind, ledger_account=ledger, created_by=user, **details)


def balance(account: BankAccount, as_of=None) -> Decimal:
    from apps.journals.models import JournalLine

    lines = JournalLine.objects.filter(account=account.ledger_account, entry__status__in=["posted", "reversed"])
    if as_of is not None:
        lines = lines.filter(entry__entry_date__lte=as_of)
    t = lines.aggregate(d=Sum("debit"), c=Sum("credit"))
    return (t["d"] or ZERO) - (t["c"] or ZERO)
