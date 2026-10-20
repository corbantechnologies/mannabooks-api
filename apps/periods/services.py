from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from apps.core.exceptions import BusinessRuleError

from .models import AccountingPeriod


def create_periods(year, user=None) -> None:
    from apps.fiscalyears.services import add_months

    periods, start = [], year.start_date
    for _ in range(12):
        end = add_months(start, 1) - timedelta(days=1)
        periods.append(AccountingPeriod(
            workspace=year.workspace, fiscal_year=year, name=start.strftime("%b %Y"),
            start_date=start, end_date=end, created_by=user,
        ))
        start = end + timedelta(days=1)
    AccountingPeriod.objects.bulk_create(periods)


def period_for(workspace, on_date) -> AccountingPeriod | None:
    return AccountingPeriod.objects.filter(workspace=workspace, start_date__lte=on_date, end_date__gte=on_date).first()


def assert_open(workspace, on_date) -> AccountingPeriod:
    """The open period that covers `on_date`; a business-rule error if there is none or it is closed."""
    period = period_for(workspace, on_date)
    if period is None:
        from datetime import timedelta

        from django.utils import timezone

        from apps.fiscalyears.models import FiscalYear
        from apps.fiscalyears.services import FURTHEST_AHEAD, ensure_years

        years = FiscalYear.objects.filter(workspace=workspace)
        last, first = years.order_by("-end_date").first(), years.order_by("start_date").first()
        if (last is None or on_date > last.end_date) and on_date <= timezone.localdate() + timedelta(days=FURTHEST_AHEAD):
            ensure_years(workspace, on_date)  # the next year, made on the spot
            period = period_for(workspace, on_date)
        if period is None:
            if first is not None and on_date < first.start_date:
                raise BusinessRuleError(
                    f"{on_date:%d %b %Y} is before your first financial year ({first.name}). If you are entering older "
                    "transactions, add the previous year in Accounting > Financial years first.",
                    code="period_missing", data={"date": on_date.isoformat()},
                )
            raise BusinessRuleError(f"{on_date:%d %b %Y} is too far ahead. Use today's date or a date within the next year.")
    if period.status == AccountingPeriod.Status.CLOSED:
        raise BusinessRuleError(f"{period.name} is closed. Reopen it, or use a date in an open period.",
                                code="period_closed", data={"date": on_date.isoformat(), "period": period.name})
    return period


def close_period(period: AccountingPeriod, user=None) -> AccountingPeriod:
    period.status = AccountingPeriod.Status.CLOSED
    period.closed_at, period.closed_by = timezone.now(), user
    period.save(update_fields=["status", "closed_at", "closed_by", "updated_at"])
    return period


def reopen_period(period: AccountingPeriod, user=None) -> AccountingPeriod:
    if period.fiscal_year.status == "closed":
        raise BusinessRuleError(f"{period.fiscal_year.name} is closed. Reopen the financial year first.")
    period.status = AccountingPeriod.Status.OPEN
    period.closed_at, period.closed_by = None, None
    period.save(update_fields=["status", "closed_at", "closed_by", "updated_at"])
    return period


OLDEST_YEARS_BACK = 10  # KRA expects records for 5 years; allow a little more, never centuries by a typo


@transaction.atomic
def open_for(workspace, on_date, user=None) -> str:
    """
    Make `on_date` postable in one step: add the earlier financial years it needs, or reopen its closed year
    and month. Returns what was done, in words.
    """
    from apps.fiscalyears.models import FiscalYear
    from apps.fiscalyears.services import add_months, create_year, reopen_year

    done = []
    first = FiscalYear.objects.filter(workspace=workspace).order_by("start_date").first()
    if first is not None and on_date < first.start_date:
        if on_date < add_months(first.start_date, -12 * OLDEST_YEARS_BACK):
            raise BusinessRuleError(f"{on_date:%d %b %Y} is more than {OLDEST_YEARS_BACK} years back. Check the date.")
        while on_date < first.start_date:
            first = create_year(workspace, add_months(first.start_date, -12), user)
            done.append(f"added {first.name}")
    period = period_for(workspace, on_date)
    if period is None:
        raise BusinessRuleError(f"No financial year covers {on_date:%d %b %Y}.")
    year = period.fiscal_year
    if year.status == FiscalYear.Status.CLOSED:
        later = FiscalYear.objects.filter(workspace=workspace, start_date__gt=year.start_date, status=FiscalYear.Status.CLOSED).order_by("-start_date")
        for later_year in later:  # reopen from the latest back, as closing requires
            reopen_year(later_year, user)
            done.append(f"reopened {later_year.name}")
        reopen_year(year, user)
        done.append(f"reopened {year.name}")
        period.refresh_from_db()
    if period.status == AccountingPeriod.Status.CLOSED:
        reopen_period(period, user)
        done.append(f"reopened {period.name}")
    return ("Done: " + ", ".join(done) + ".") if done else f"{period.name} is already open."
