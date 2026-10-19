"""
The posting engine. Everything that reaches the ledger goes through here:

- `post_draft`: post a manual draft entry after checking it;
- `replace_for_source`: what other modules call when a record is created, changed or cancelled. Its
  earlier entries are removed if their period is open, or reversed in the current open period if not,
  and the new lines (if any) are posted;
- `reverse_entry`: a mirror-image entry that cancels a posted one.

Rules enforced every time: at least two lines, each line a debit or a credit (not both, not zero),
debits equal credits, every account active and in the same workspace, and the date in an open period.
"""
from dataclasses import dataclass, field

from django.apps import apps as django_apps
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from apps.core.exceptions import BusinessRuleError
from apps.core.money import ZERO, q2
from apps.periods.services import assert_open, period_for
from apps.sequences.services import next_value

from .models import JournalEntry, JournalLine


@dataclass
class LineInput:
    account: object
    debit: object = ZERO
    credit: object = ZERO
    description: str = ""
    branch: object = None
    department: object = None
    cost_center: object = None
    project: object = None
    extra: dict = field(default_factory=dict)


def dimensions_of(record) -> tuple:
    """A record's cost centre and project, for the income and expense lines it posts."""
    return (getattr(record, "cost_center", None), getattr(record, "project", None))


def _source_dimensions(source_model: str, source_id) -> tuple:
    if not source_id or source_model.count(".") != 1:
        return (None, None)
    try:
        model = django_apps.get_model(source_model)
    except (LookupError, ValueError):
        return (None, None)
    if not {"cost_center", "project"} & {f.name for f in model._meta.fields}:
        return (None, None)
    try:
        record = model.objects.filter(pk=source_id).first()
    except (ValueError, ValidationError):  # not one of that model's ids
        return (None, None)
    return dimensions_of(record) if record is not None else (None, None)


def _tag(lines: list[LineInput], dimensions) -> None:
    """Put the cost centre and project on income and expense lines that don't have their own."""
    cost_center, project = dimensions
    if cost_center is None and project is None:
        return
    for line in lines:
        if line.account.account_type in ("income", "expense"):
            line.cost_center = line.cost_center or cost_center
            line.project = line.project or project


def check_lines(workspace, lines: list[LineInput]) -> None:
    if len(lines) < 2:
        raise BusinessRuleError("A journal entry needs at least two lines.")
    total_debit = total_credit = ZERO
    for n, line in enumerate(lines, start=1):
        debit, credit = q2(line.debit), q2(line.credit)
        if debit < 0 or credit < 0:
            raise BusinessRuleError(f"Line {n}: amounts can't be negative.")
        if (debit > 0) == (credit > 0):
            raise BusinessRuleError(f"Line {n}: enter either a debit or a credit.")
        if line.account.workspace_id != workspace.id:
            raise BusinessRuleError(f"Line {n}: that account belongs to another workspace.")
        if not line.account.is_active:
            raise BusinessRuleError(f"Line {n}: {line.account} is inactive.")
        total_debit += debit
        total_credit += credit
    if total_debit != total_credit:
        raise BusinessRuleError(
            f"Debits ({total_debit:,.2f}) and credits ({total_credit:,.2f}) must be equal. "
            f"The difference is {abs(total_debit - total_credit):,.2f}."
        )


def lines_of(entry: JournalEntry) -> list[LineInput]:
    return [
        LineInput(account=line.account, debit=line.debit, credit=line.credit, description=line.description,
                  branch=line.branch, department=line.department, cost_center=line.cost_center, project=line.project)
        for line in entry.lines.select_related("account", "cost_center", "project")
    ]


def _write_lines(entry: JournalEntry, lines: list[LineInput]) -> None:
    JournalLine.objects.bulk_create(
        JournalLine(
            entry=entry, account=line.account, debit=q2(line.debit), credit=q2(line.credit),
            description=line.description[:255], branch=line.branch, department=line.department, cost_center=line.cost_center,
            project=line.project, line_no=n,
        )
        for n, line in enumerate(lines, start=1)
    )


def _mark_posted(entry: JournalEntry, user=None) -> JournalEntry:
    entry.period = assert_open(entry.workspace, entry.entry_date)
    entry.number = next_value(entry.workspace, "journal")
    entry.status = JournalEntry.Status.POSTED
    entry.posted_at, entry.posted_by = timezone.now(), user
    entry.save(update_fields=["period", "number", "status", "posted_at", "posted_by", "updated_at"])
    return entry


@transaction.atomic
def create_draft(workspace, *, entry_date, description, lines: list[LineInput], reference="", user=None) -> JournalEntry:
    entry = JournalEntry.objects.create(
        workspace=workspace, entry_date=entry_date, description=description, reference=reference, created_by=user
    )
    _write_lines(entry, lines)
    return entry


@transaction.atomic
def update_draft(entry: JournalEntry, *, lines: list[LineInput] | None = None, **fields) -> JournalEntry:
    if entry.status != JournalEntry.Status.DRAFT:
        raise BusinessRuleError("Only draft entries can be edited. Reverse a posted entry instead.")
    for key, value in fields.items():
        setattr(entry, key, value)
    entry.save()
    if lines is not None:
        entry.lines.all().delete()
        _write_lines(entry, lines)
    return entry


@transaction.atomic
def post_draft(entry: JournalEntry, user=None) -> JournalEntry:
    entry = JournalEntry.objects.select_for_update().get(pk=entry.pk)
    if entry.status != JournalEntry.Status.DRAFT:
        raise BusinessRuleError("This entry is already posted.")
    check_lines(entry.workspace, lines_of(entry))
    return _mark_posted(entry, user)


@transaction.atomic
def post_lines(workspace, *, entry_date, description, lines, source, source_model="", source_id="", reference="", user=None,
               dimensions=None) -> JournalEntry:
    """
    Check and post an entry in one step (for system postings). Income and expense lines take the source
    record's cost centre and project unless `dimensions` (cost centre, project) says otherwise.
    """
    check_lines(workspace, lines)
    _tag(lines, dimensions if dimensions is not None else _source_dimensions(source_model, source_id))
    assert_open(workspace, entry_date)
    entry = JournalEntry.objects.create(
        workspace=workspace, entry_date=entry_date, description=description[:255], reference=reference,
        source=source, source_model=source_model, source_id=source_id, created_by=user,
    )
    _write_lines(entry, lines)
    return _mark_posted(entry, user)


@transaction.atomic
def reverse_entry(entry: JournalEntry, *, entry_date, user=None, reason="") -> JournalEntry:
    if entry.status != JournalEntry.Status.POSTED:
        raise BusinessRuleError("Only posted entries can be reversed.")
    if hasattr(entry, "reversed_by"):
        raise BusinessRuleError("This entry has already been reversed.")
    mirror = [
        LineInput(account=line.account, debit=line.credit, credit=line.debit, description=line.description,
                  branch=line.branch, department=line.department, cost_center=line.cost_center, project=line.project)
        for line in lines_of(entry)
    ]
    reversal = post_lines(
        entry.workspace, entry_date=entry_date,
        description=f"Reversal of {entry.number}" + (f": {reason}" if reason else ""),
        lines=mirror, source=entry.source, source_model=entry.source_model, source_id=entry.source_id,
        reference=entry.number, user=user, dimensions=(None, None),
    )
    reversal.reversal_of = entry
    reversal.save(update_fields=["reversal_of", "updated_at"])
    entry.status = JournalEntry.Status.REVERSED
    entry.save(update_fields=["status", "updated_at"])
    return reversal


@transaction.atomic
def replace_for_source(workspace, *, source, source_model, source_id, entry_date, description, lines, reference="", user=None, dimensions=None):
    """
    Make the ledger match a record's current state. Its earlier entries are deleted when their period is
    open, or reversed today when it is closed; then `lines` (if any) are posted. Returns the new entry.
    """
    earlier = JournalEntry.objects.filter(
        workspace=workspace, source_model=source_model, source_id=source_id, status=JournalEntry.Status.POSTED,
        reversal_of__isnull=True,
    )
    from apps.reconciliations.models import ReconciledLine

    done = ReconciledLine.objects.filter(journal_line__entry__in=earlier, reconciliation__status="completed").select_related("reconciliation").first()
    if done is not None:
        raise BusinessRuleError(f"This transaction is in the bank reconciliation of {done.reconciliation}. Reopen that reconciliation first.")
    ReconciledLine.objects.filter(journal_line__entry__in=earlier).delete()  # ticks in a reconciliation still in progress
    for entry in earlier:
        period = period_for(workspace, entry.entry_date)
        if period is not None and period.status == "open":
            entry.delete()
        else:
            reverse_entry(entry, entry_date=timezone.localdate(), user=user, reason="record changed")
    if not lines:
        return None
    return post_lines(
        workspace, entry_date=entry_date, description=description, lines=lines, source=source,
        source_model=source_model, source_id=source_id, reference=reference, user=user, dimensions=dimensions,
    )
