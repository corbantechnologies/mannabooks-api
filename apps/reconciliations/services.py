from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from apps.core.exceptions import BusinessRuleError
from apps.core.money import ZERO
from apps.journals.models import JournalLine

from .models import ReconciledLine, Reconciliation

S = Reconciliation.Status


def start(account, *, statement_date, statement_balance, user=None) -> Reconciliation:
    if Reconciliation.objects.filter(bank_account=account, status=S.IN_PROGRESS).exists():
        raise BusinessRuleError(f"A reconciliation of {account} is already in progress. Finish or delete it first.")
    last = Reconciliation.objects.filter(bank_account=account, status=S.COMPLETED).order_by("-statement_date").first()
    if last and statement_date <= last.statement_date:
        raise BusinessRuleError(f"{account} is reconciled up to {last.statement_date:%d %b %Y}. Choose a later statement date.")
    rec = Reconciliation.objects.create(workspace=account.workspace, created_by=user, bank_account=account, statement_date=statement_date,
                                        statement_balance=statement_balance, opening_balance=last.statement_balance if last else ZERO)
    # tick everything already matched to statement lines up to the date
    matched = JournalLine.objects.filter(statement_lines__bank_account=account, statement_lines__status="matched",
                                         entry__entry_date__lte=statement_date, reconciled__isnull=True)
    ReconciledLine.objects.bulk_create(ReconciledLine(reconciliation=rec, journal_line=jl) for jl in matched)
    return rec


def candidates(rec: Reconciliation):
    """Transactions in the account up to the statement date that no finished reconciliation has cleared
    (for a finished one: the transactions it cleared)."""
    if rec.status == S.COMPLETED:
        return JournalLine.objects.filter(reconciled__reconciliation=rec).select_related("entry").order_by("entry__entry_date", "entry__created_at")
    return (JournalLine.objects.filter(account=rec.bank_account.ledger_account, entry__status__in=["posted", "reversed"],
                                       entry__entry_date__lte=rec.statement_date)
            .exclude(reconciled__reconciliation__status=S.COMPLETED)
            .select_related("entry").order_by("entry__entry_date", "entry__created_at"))


def cleared_total(rec: Reconciliation):
    t = JournalLine.objects.filter(reconciled__reconciliation=rec).aggregate(d=Sum("debit"), c=Sum("credit"))
    return (t["d"] or ZERO) - (t["c"] or ZERO)


def summary(rec: Reconciliation) -> dict:
    cleared = rec.opening_balance + cleared_total(rec)
    return {"cleared_balance": cleared, "difference": rec.statement_balance - cleared}


@transaction.atomic
def tick(rec: Reconciliation, journal_line_ids: list, cleared: bool) -> Reconciliation:
    if rec.status != S.IN_PROGRESS:
        raise BusinessRuleError("This reconciliation is finished.")
    lines = candidates(rec).filter(pk__in=journal_line_ids)
    if cleared:
        have = set(ReconciledLine.objects.filter(reconciliation=rec).values_list("journal_line_id", flat=True))
        ReconciledLine.objects.bulk_create(ReconciledLine(reconciliation=rec, journal_line=jl) for jl in lines if jl.pk not in have)
    else:
        ReconciledLine.objects.filter(reconciliation=rec, journal_line__in=lines).delete()
    return rec


@transaction.atomic
def complete(rec: Reconciliation, user=None) -> Reconciliation:
    if rec.status != S.IN_PROGRESS:
        raise BusinessRuleError("This reconciliation is already finished.")
    diff = summary(rec)["difference"]
    if diff:
        raise BusinessRuleError(f"The books and the statement differ by {diff:,.2f}. Tick the cleared transactions, or record what's missing.")
    rec.status, rec.completed_at, rec.completed_by = S.COMPLETED, timezone.now(), user
    rec.save(update_fields=["status", "completed_at", "completed_by", "updated_at"])
    return rec


@transaction.atomic
def reopen(rec: Reconciliation) -> Reconciliation:
    if rec.status != S.COMPLETED:
        raise BusinessRuleError("Only a finished reconciliation can be reopened.")
    if Reconciliation.objects.filter(bank_account=rec.bank_account, statement_date__gt=rec.statement_date).exists():
        raise BusinessRuleError("Undo the later reconciliations first.")
    if Reconciliation.objects.filter(bank_account=rec.bank_account, status=S.IN_PROGRESS).exists():
        raise BusinessRuleError("Finish or delete the reconciliation in progress first.")
    rec.status, rec.completed_at = S.IN_PROGRESS, None
    rec.save(update_fields=["status", "completed_at", "updated_at"])
    return rec
