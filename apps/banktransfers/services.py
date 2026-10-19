from django.db import transaction

from apps.core.exceptions import BusinessRuleError
from apps.core.money import q2
from apps.journals.services import LineInput, replace_for_source
from apps.ledgeraccounts.services import system_account
from apps.sequences.services import next_value

from .models import BankTransfer

SOURCE = {"source": "bank_transfer", "source_model": "banktransfers.BankTransfer"}


@transaction.atomic
def create(workspace, *, from_account, to_account, transfer_date, amount, fee=0, reference="", notes="", user=None) -> BankTransfer:
    amount, fee = q2(amount), q2(fee or 0)
    if from_account == to_account:
        raise BusinessRuleError("Choose two different accounts.")
    if amount <= 0 or fee < 0:
        raise BusinessRuleError("Enter the amount moved (and any charge).")
    t = BankTransfer.objects.create(workspace=workspace, created_by=user, number=next_value(workspace, "bank_transfer"), from_account=from_account,
                                    to_account=to_account, transfer_date=transfer_date, amount=amount, fee=fee, reference=reference, notes=notes)
    label = f"Transfer {t.number}: {from_account} to {to_account}"
    lines = [LineInput(account=to_account.ledger_account, debit=amount, description=label),
             LineInput(account=from_account.ledger_account, credit=amount + fee, description=label)]
    if fee:
        lines.append(LineInput(account=system_account(workspace, "bank_charges"), debit=fee, description=f"{label}: charge"))
    replace_for_source(workspace, **SOURCE, source_id=str(t.pk), entry_date=transfer_date, reference=t.number, description=label, lines=lines, user=user)
    return t


@transaction.atomic
def void(t: BankTransfer, user=None) -> BankTransfer:
    if t.status == BankTransfer.Status.VOID:
        raise BusinessRuleError("Already void.")
    replace_for_source(t.workspace, **SOURCE, source_id=str(t.pk), entry_date=t.transfer_date, description="", lines=[], user=user)
    t.status = BankTransfer.Status.VOID
    t.save(update_fields=["status", "updated_at"])
    return t
