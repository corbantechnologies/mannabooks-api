import calendar
from datetime import date, timedelta

from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from apps.core.exceptions import BusinessRuleError
from apps.core.money import ZERO

from .models import FiscalYear


def add_months(d: date, months: int) -> date:
    month = d.month - 1 + months
    year = d.year + month // 12
    month = month % 12 + 1
    return date(year, month, min(d.day, calendar.monthrange(year, month)[1]))


def year_name(start: date, end: date) -> str:
    return f"FY{start.year}" if start.year == end.year else f"FY{start.year}/{str(end.year)[2:]}"


@transaction.atomic
def create_year(workspace, start: date, user=None) -> FiscalYear:
    """A 12-month year from `start`, with its 12 periods. Years must not overlap."""
    from apps.periods.services import create_periods

    end = add_months(start, 12) - timedelta(days=1)
    if FiscalYear.objects.filter(workspace=workspace, start_date__lte=end, end_date__gte=start).exists():
        raise BusinessRuleError(f"A financial year already covers part of {start} to {end}.")
    year = FiscalYear.objects.create(workspace=workspace, name=year_name(start, end), start_date=start, end_date=end, created_by=user)
    create_periods(year, user)
    return year


def first_year_start(workspace, today: date | None = None) -> date:
    """The start of the financial year that contains `today`, given the workspace's start month."""
    today = today or timezone.localdate()
    start = date(today.year, workspace.fiscal_year_start_month, 1)
    return start if start <= today else date(today.year - 1, workspace.fiscal_year_start_month, 1)


def create_initial_year(workspace, user=None) -> FiscalYear:
    return create_year(workspace, first_year_start(workspace), user)


def create_adjacent_year(workspace, position: str, user=None) -> FiscalYear:
    """The year right after the latest one ("next") or right before the earliest ("previous")."""
    years = FiscalYear.objects.filter(workspace=workspace)
    if not years.exists():
        return create_initial_year(workspace, user)
    if position == "previous":
        earliest = years.order_by("start_date").first()
        return create_year(workspace, add_months(earliest.start_date, -12), user)
    latest = years.order_by("-start_date").first()
    return create_year(workspace, latest.end_date + timedelta(days=1), user)


@transaction.atomic
def close_year(year: FiscalYear, user=None) -> FiscalYear:
    """
    Post the closing entry (income and expense balances to retained earnings, dated the last day of the
    year), then close every period of the year.
    """
    from apps.journals.models import JournalLine
    from apps.journals.services import LineInput, replace_for_source
    from apps.ledgeraccounts.services import system_account

    if year.status == FiscalYear.Status.CLOSED:
        raise BusinessRuleError(f"{year.name} is already closed.")
    earlier_open = FiscalYear.objects.filter(
        workspace=year.workspace, start_date__lt=year.start_date, status=FiscalYear.Status.OPEN
    )
    if earlier_open.exists():
        raise BusinessRuleError("Close the earlier financial years first.")

    totals = (
        JournalLine.objects.filter(
            entry__workspace=year.workspace,
            entry__status__in=["posted", "reversed"],  # a reversed entry still counts; its reversal cancels it
            entry__entry_date__range=(year.start_date, year.end_date),
            account__account_type__in=["income", "expense"],
        )
        .exclude(entry__source="year_end")
        .values("account")
        .annotate(debit=Sum("debit"), credit=Sum("credit"))
    )
    from apps.ledgeraccounts.models import LedgerAccount

    accounts = LedgerAccount.objects.in_bulk([t["account"] for t in totals])
    lines, profit = [], ZERO
    for t in totals:
        net = (t["debit"] or ZERO) - (t["credit"] or ZERO)  # positive: debit balance (expense-like)
        if net == ZERO:
            continue
        account = accounts[t["account"]]
        lines.append(LineInput(account=account, debit=ZERO if net > 0 else -net, credit=net if net > 0 else ZERO,
                               description=f"Close {account.name} for {year.name}"))
        profit -= net
    if lines:
        retained = system_account(year.workspace, "retained_earnings")
        lines.append(LineInput(account=retained, debit=-profit if profit < 0 else ZERO, credit=profit if profit > 0 else ZERO,
                               description=f"{'Profit' if profit >= 0 else 'Loss'} for {year.name}"))
    replace_for_source(
        year.workspace, source="year_end", source_model="fiscalyears.FiscalYear", source_id=str(year.pk),
        entry_date=year.end_date, description=f"Year-end close {year.name}", lines=lines, user=user,
    )
    year.periods.update(status="closed", closed_at=timezone.now(), closed_by=user)
    year.status = FiscalYear.Status.CLOSED
    year.closed_at, year.closed_by = timezone.now(), user
    year.save(update_fields=["status", "closed_at", "closed_by", "updated_at"])
    return year


@transaction.atomic
def reopen_year(year: FiscalYear, user=None) -> FiscalYear:
    """Reopen the latest closed year: its last period opens and the closing entry is removed."""
    from apps.journals.services import replace_for_source

    if year.status != FiscalYear.Status.CLOSED:
        raise BusinessRuleError(f"{year.name} is not closed.")
    if FiscalYear.objects.filter(workspace=year.workspace, start_date__gt=year.start_date, status=FiscalYear.Status.CLOSED).exists():
        raise BusinessRuleError("Reopen the later closed years first.")
    year.status = FiscalYear.Status.OPEN
    year.closed_at, year.closed_by = None, None
    year.save(update_fields=["status", "closed_at", "closed_by", "updated_at"])
    year.periods.filter(end_date=year.end_date).update(status="open", closed_at=None, closed_by=None)
    replace_for_source(
        year.workspace, source="year_end", source_model="fiscalyears.FiscalYear", source_id=str(year.pk),
        entry_date=year.end_date, description="", lines=[], user=user,
    )
    return year


AHEAD_DAYS = 31  # the next year exists a month before the current one ends
FURTHEST_AHEAD = 400  # never create years for dates more than about a year away


@transaction.atomic
def ensure_years(workspace, until: date, user=None) -> list[FiscalYear]:
    """Create the following financial years, in order, until one covers `until`. Returns the years made."""
    from apps.workspaces.models import Workspace

    Workspace.objects.select_for_update().filter(pk=workspace.pk).first()  # one roll-forward per workspace at a time
    latest = FiscalYear.objects.filter(workspace=workspace).order_by("-start_date").first()
    made = []
    if latest is None:
        latest = create_initial_year(workspace, user)
        made.append(latest)
    while latest.end_date < until:
        latest = create_year(workspace, latest.end_date + timedelta(days=1), user)
        made.append(latest)
    return made


def roll_forward_all(today: date | None = None) -> int:
    """Nightly: every workspace has its next financial year ready before the current one ends."""
    from apps.workspaces.models import Workspace

    today = today or timezone.localdate()
    made = 0
    for workspace in Workspace.objects.filter(is_active=True):
        made += len(ensure_years(workspace, today + timedelta(days=AHEAD_DAYS)))
    return made


def ended_unclosed(workspace, today: date | None = None) -> list[FiscalYear]:
    """Years that have ended but are still open: the accountant should close them once the books are final."""
    today = today or timezone.localdate()
    return list(FiscalYear.objects.filter(workspace=workspace, status=FiscalYear.Status.OPEN, end_date__lt=today).order_by("start_date"))


@transaction.atomic
def restart_years(workspace, user=None) -> None:
    """After the start month changes (allowed only before anything is posted): rebuild the years from scratch."""
    from apps.journals.models import JournalEntry

    if JournalEntry.objects.filter(workspace=workspace).exists():
        raise BusinessRuleError("The financial year's start month can't change once transactions are posted.")
    FiscalYear.objects.filter(workspace=workspace).delete()
    ensure_years(workspace, timezone.localdate() + timedelta(days=AHEAD_DAYS), user)
