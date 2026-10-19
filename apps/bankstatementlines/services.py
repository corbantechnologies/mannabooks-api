import uuid
from datetime import timedelta
from decimal import Decimal

from django.db import transaction
from django.db.models.signals import pre_delete
from django.dispatch import receiver

from apps.core.exceptions import BusinessRuleError
from apps.core.money import q2
from apps.journals.models import JournalLine

from .models import BankStatementLine

S = BankStatementLine.Status


@receiver(pre_delete, sender=JournalLine)
def _unmatch(sender, instance, **kwargs):
    """A transaction removed from the books (document voided or changed) frees its statement line."""
    BankStatementLine.objects.filter(journal_line_id=instance.pk).update(status=S.UNMATCHED, journal_line=None)


@transaction.atomic
def import_lines(account, rows: list[dict]) -> list[BankStatementLine]:
    """Add statement lines; a line already imported (same date, amount and reference or description) is skipped."""
    batch = uuid.uuid4().hex[:12]
    created = []
    for row in rows:
        amount = q2(row["amount"])
        if not amount:
            continue
        dup = BankStatementLine.objects.filter(bank_account=account, line_date=row["line_date"], amount=amount)
        dup = dup.filter(reference=row["reference"]) if row.get("reference") else dup.filter(description=row["description"][:255])
        if dup.exists():
            continue
        created.append(BankStatementLine.objects.create(workspace=account.workspace, bank_account=account, line_date=row["line_date"],
                                                        description=row["description"][:255], reference=(row.get("reference") or "")[:80],
                                                        amount=amount, import_batch=batch))
    return created


def taken_lines():
    return BankStatementLine.objects.filter(journal_line__isnull=False).values("journal_line_id")


def suggestions(line: BankStatementLine, days: int = 10):
    """Unmatched transactions in the books with the same amount, nearest date first."""
    ledger = line.bank_account.ledger_account
    field = "debit" if line.amount > 0 else "credit"
    qs = (JournalLine.objects.filter(account=ledger, entry__status__in=["posted", "reversed"], **{field: abs(line.amount)},
                                     entry__entry_date__range=(line.line_date - timedelta(days=days), line.line_date + timedelta(days=days)))
          .exclude(pk__in=taken_lines()).select_related("entry"))
    return sorted(qs, key=lambda j: abs((j.entry.entry_date - line.line_date).days))


@transaction.atomic
def match(line: BankStatementLine, journal_line: JournalLine) -> BankStatementLine:
    if line.status == S.MATCHED:
        raise BusinessRuleError("This line is already matched.")
    if journal_line.account_id != line.bank_account.ledger_account_id:
        raise BusinessRuleError("That transaction is in another account.")
    if (journal_line.debit - journal_line.credit) != line.amount:
        raise BusinessRuleError("The amounts are different.")
    if BankStatementLine.objects.filter(journal_line=journal_line).exists():
        raise BusinessRuleError("That transaction is matched to another statement line.")
    line.journal_line, line.status = journal_line, S.MATCHED
    line.save(update_fields=["journal_line", "status", "updated_at"])
    return line


def unmatch(line: BankStatementLine) -> BankStatementLine:
    from apps.reconciliations.models import ReconciledLine

    if line.journal_line_id and ReconciledLine.objects.filter(journal_line_id=line.journal_line_id, reconciliation__status="completed").exists():
        raise BusinessRuleError("This transaction is in a finished reconciliation.")
    line.journal_line, line.status = None, S.UNMATCHED
    line.save(update_fields=["journal_line", "status", "updated_at"])
    return line


@transaction.atomic
def create_transaction(line: BankStatementLine, *, account, tax_rate=None, description="", user=None):
    """Record a statement line that isn't in the books yet (bank charges, interest...) as an expense or other income, and match it."""
    from apps.expenses.services import create as create_expense
    from apps.otherincomes.services import create as create_income

    if line.status != S.UNMATCHED:
        raise BusinessRuleError("Only an unmatched line can be recorded.")
    text = description or line.description
    if line.amount < 0:
        doc = create_expense(line.workspace, paid_from=line.bank_account, expense_date=line.line_date, user=user, payee=text[:150],
                             reference=line.reference[:60], prices_include_tax=True,
                             rows=[{"description": text, "quantity": Decimal(1), "unit_cost": -line.amount, "tax_rate": tax_rate, "account": account}])
        source_model = "expenses.Expense"
    else:
        doc = create_income(line.workspace, received_into=line.bank_account, income_date=line.line_date, user=user, payer=text[:150],
                            reference=line.reference[:60], rows=[{"description": text, "amount": line.amount, "tax_rate": tax_rate, "account": account}])
        source_model = "otherincomes.OtherIncome"
    jl = JournalLine.objects.get(entry__source_model=source_model, entry__source_id=str(doc.pk), account=line.bank_account.ledger_account)
    match(line, jl)
    return doc
