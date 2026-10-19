from django.db import transaction

from apps.core.exceptions import BusinessRuleError
from apps.core.money import ZERO
from apps.core.sales import price
from apps.journals.services import LineInput, replace_for_source
from apps.ledgeraccounts.services import system_account
from apps.sequences.services import next_value

from .models import OtherIncome, OtherIncomeLine

SOURCE = {"source": "other_income", "source_model": "otherincomes.OtherIncome"}


@transaction.atomic
def create(workspace, *, received_into, income_date, rows, prices_include_tax=True, user=None, **details) -> OtherIncome:
    if not rows:
        raise BusinessRuleError("Add at least one line.")
    income = OtherIncome.objects.create(workspace=workspace, created_by=user, number=next_value(workspace, "other_income"),
                                        received_into=received_into, income_date=income_date, prices_include_tax=prices_include_tax, **details)
    credits, subtotal, tax_total, total = {}, ZERO, ZERO, ZERO
    for n, row in enumerate(rows, start=1):
        account = row.get("account") or system_account(workspace, "other_income")
        if account.account_type != "income" or not account.is_active:
            raise BusinessRuleError(f"Line {n}: record it in an active income account.")
        tax_rate = row.get("tax_rate")
        if tax_rate is not None and (tax_rate.kind != "vat" or tax_rate.sales_account is None):
            raise BusinessRuleError(f"Line {n}: choose a VAT rate with an output VAT account.")
        net, tax, gross = price(1, row["amount"], 0, tax_rate, prices_include_tax)
        OtherIncomeLine.objects.create(income=income, description=(row.get("description") or account.name)[:255], account=account,
                                       tax_rate=tax_rate, amount=row["amount"], net_amount=net, tax_amount=tax, total_amount=gross)
        credits[account] = credits.get(account, ZERO) + net
        if tax:
            credits[tax_rate.sales_account] = credits.get(tax_rate.sales_account, ZERO) + tax
        subtotal, tax_total, total = subtotal + net, tax_total + tax, total + gross
    if total <= 0:
        raise BusinessRuleError("Enter what was received.")
    income.subtotal, income.tax_total, income.total = subtotal, tax_total, total
    income.save(update_fields=["subtotal", "tax_total", "total", "updated_at"])
    label = f"{income.number} {income.payer}".strip()
    journal = [LineInput(account=received_into.ledger_account, debit=total, description=label)]
    journal += [LineInput(account=a, credit=v, description=label) for a, v in credits.items() if v]
    replace_for_source(workspace, **SOURCE, source_id=str(income.pk), entry_date=income_date, reference=income.number,
                       description=f"Other income {label}", lines=journal, user=user)
    return income


@transaction.atomic
def void(income: OtherIncome, reason: str, user=None) -> OtherIncome:
    if income.status == OtherIncome.Status.VOID:
        raise BusinessRuleError("Already void.")
    replace_for_source(income.workspace, **SOURCE, source_id=str(income.pk), entry_date=income.income_date, description="", lines=[], user=user)
    income.status, income.void_reason = OtherIncome.Status.VOID, reason[:255]
    income.save(update_fields=["status", "void_reason", "updated_at"])
    return income
