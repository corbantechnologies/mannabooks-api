from datetime import timedelta

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
        raise BusinessRuleError(
            f"No accounting period covers {on_date:%d %b %Y}. Add the financial year in Financial years first."
        )
    if period.status == AccountingPeriod.Status.CLOSED:
        raise BusinessRuleError(f"{period.name} is closed. Reopen it, or use a date in an open period.")
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
