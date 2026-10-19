from django.db import transaction

from apps.core import purchases
from apps.core.exceptions import BusinessRuleError
from apps.core.money import ZERO
from apps.journals.services import LineInput, replace_for_source
from apps.sequences.services import next_value

from .models import Expense, ExpenseLine

SOURCE = {"source": "expense", "source_model": "expenses.Expense"}


@transaction.atomic
def create(workspace, *, paid_from, expense_date, rows, prices_include_tax=True, user=None, **details) -> Expense:
    if not paid_from.is_active:
        raise BusinessRuleError(f"{paid_from} is closed.")
    expense = Expense.objects.create(workspace=workspace, created_by=user, number=next_value(workspace, "expense"), paid_from=paid_from,
                                     expense_date=expense_date, prices_include_tax=prices_include_tax, **details)
    lines = purchases.write_lines(expense, ExpenseLine, "expense", purchases.resolve_lines(workspace, rows))
    if expense.total <= 0:
        raise BusinessRuleError("Enter what was spent.")
    label = f"{expense.number} {expense.payee or (expense.supplier or '')}".strip()
    debits = {}
    for line in lines:
        debits[line.account] = debits.get(line.account, ZERO) + line.net_amount
        if line.tax_amount:
            if line.tax_rate.purchases_account is None:
                raise BusinessRuleError(f"{line.tax_rate} has no account for VAT on purchases.")
            debits[line.tax_rate.purchases_account] = debits.get(line.tax_rate.purchases_account, ZERO) + line.tax_amount
    journal = [LineInput(account=a, debit=v, description=label) for a, v in debits.items() if v]
    journal.append(LineInput(account=paid_from.ledger_account, credit=expense.total, description=label))
    replace_for_source(workspace, **SOURCE, source_id=str(expense.pk), entry_date=expense_date, reference=expense.number,
                       description=f"Expense {label}", lines=journal, user=user)
    return expense


@transaction.atomic
def void(expense: Expense, reason: str, user=None) -> Expense:
    if expense.status == Expense.Status.VOID:
        raise BusinessRuleError("This expense is already void.")
    replace_for_source(expense.workspace, **SOURCE, source_id=str(expense.pk), entry_date=expense.expense_date, description="", lines=[], user=user)
    expense.status, expense.void_reason = Expense.Status.VOID, reason[:255]
    expense.save(update_fields=["status", "void_reason", "updated_at"])
    return expense
