from decimal import Decimal as D

import pytest

from apps.fiscalyears.models import FiscalYear
from apps.journals import services
from apps.ledgeraccounts.models import LedgerAccount
from apps.reports.services import trial_balance

pytestmark = pytest.mark.django_db


def acc(ws, code):
    return LedgerAccount.objects.get(workspace=ws, code=code)


def test_adding_years_keeps_them_contiguous(workspace, owner, client_for):
    api = client_for(owner)
    url = f"/api/v1/w/{workspace.slug}/fiscal-years/"
    first = FiscalYear.objects.get(workspace=workspace)
    nxt = api.post(url, {"position": "next"}, format="json").data
    prev = api.post(url, {"position": "previous"}, format="json").data
    assert nxt["start_date"] > first.end_date.isoformat() and prev["end_date"] < first.start_date.isoformat()
    assert len(api.get(url).data) == 3


def test_closing_a_year_moves_profit_to_retained_earnings(workspace, owner, client_for):
    year = FiscalYear.objects.get(workspace=workspace)
    day = year.start_date
    services.post_lines(workspace, entry_date=day, description="Cash sale", source="manual", lines=[
        services.LineInput(account=acc(workspace, "1000"), debit=1000), services.LineInput(account=acc(workspace, "4000"), credit=1000)])
    services.post_lines(workspace, entry_date=day, description="Rent", source="manual", lines=[
        services.LineInput(account=acc(workspace, "6010"), debit=300), services.LineInput(account=acc(workspace, "1000"), credit=300)])
    api = client_for(owner)
    res = api.post(f"/api/v1/w/{workspace.slug}/fiscal-years/{year.id}/close/")
    assert res.status_code == 200 and res.data["status"] == "closed" and res.data["open_periods"] == 0

    tb = {r["code"]: r for r in trial_balance(workspace, year.end_date)["rows"]}
    assert "4000" not in tb and "6010" not in tb
    assert tb["3100"]["credit"] == D("700.00")

    blocked = services.post_lines  # posting into the closed year is refused
    with pytest.raises(Exception, match="closed"):
        blocked(workspace, entry_date=day, description="late", source="manual", lines=[
            services.LineInput(account=acc(workspace, "1000"), debit=1), services.LineInput(account=acc(workspace, "4000"), credit=1)])

    reopened = api.post(f"/api/v1/w/{workspace.slug}/fiscal-years/{year.id}/reopen/")
    assert reopened.data["status"] == "open"
    assert "3100" not in {r["code"] for r in trial_balance(workspace, year.end_date)["rows"]}


def test_years_roll_forward_and_backdating_stays_deliberate(workspace, owner, client_for):
    from datetime import timedelta

    from django.utils import timezone

    from apps.core.exceptions import BusinessRuleError
    from apps.fiscalyears.services import ended_unclosed, roll_forward_all
    from apps.periods.services import assert_open

    first = FiscalYear.objects.get(workspace=workspace)
    soon = first.end_date + timedelta(days=5)
    assert assert_open(workspace, soon).start_date <= soon  # the next year is made on the spot
    assert FiscalYear.objects.filter(workspace=workspace).count() == 2
    with pytest.raises(BusinessRuleError, match="before your first financial year"):
        assert_open(workspace, first.start_date - timedelta(days=1))
    with pytest.raises(BusinessRuleError, match="too far ahead"):
        assert_open(workspace, timezone.localdate() + timedelta(days=900))
    assert roll_forward_all(today=first.end_date + timedelta(days=360)) >= 0  # nightly job: nothing breaks, years stay contiguous
    years = list(FiscalYear.objects.filter(workspace=workspace).order_by("start_date"))
    assert all(a.end_date + timedelta(days=1) == b.start_date for a, b in zip(years, years[1:], strict=False))
    assert [y.name for y in ended_unclosed(workspace, today=first.end_date + timedelta(days=1))] == [first.name]


def test_start_month_locks_once_posted(workspace, owner, client_for):
    api = client_for(owner)
    url = f"/api/v1/w/{workspace.slug}/"
    moved = api.patch(url, {"fiscal_year_start_month": 7}, format="json")
    assert moved.status_code == 200
    assert FiscalYear.objects.get(workspace=workspace).start_date.month == 7  # rebuilt, nothing posted yet
    cash, sales = (LedgerAccount.objects.get(workspace=workspace, code=c) for c in ("1000", "4000"))
    entry = services.create_draft(workspace, entry_date=FiscalYear.objects.get(workspace=workspace).start_date, description="Sale",
                                  lines=[services.LineInput(account=cash, debit=D("100")), services.LineInput(account=sales, credit=D("100"))])
    services.post_draft(entry)
    assert api.patch(url, {"fiscal_year_start_month": 1}, format="json").status_code == 400


def test_open_books_for_an_earlier_or_closed_date(workspace, owner, client_for):
    from datetime import timedelta

    from apps.periods.models import AccountingPeriod

    api = client_for(owner)
    first = FiscalYear.objects.get(workspace=workspace)
    cash, sales = (LedgerAccount.objects.get(workspace=workspace, code=c) for c in ("1000", "4000"))
    old = first.start_date - timedelta(days=200)

    def post(on):
        entry = api.post(f"/api/v1/w/{workspace.slug}/journals/", {"entry_date": on.isoformat(), "description": "Old sale", "lines": [
            {"account_id": str(cash.id), "debit": "100"}, {"account_id": str(sales.id), "credit": "100"}]}, format="json").data
        return api.post(f"/api/v1/w/{workspace.slug}/journals/{entry['id']}/post/")

    blocked = post(old)
    assert blocked.status_code == 409 and blocked.data["code"] == "period_missing" and blocked.data["data"]["date"] == old.isoformat()
    fixed = api.post(f"/api/v1/w/{workspace.slug}/periods/open-for-date/", {"date": old.isoformat()}, format="json")
    assert fixed.status_code == 200 and "added" in fixed.data["message"]
    assert post(old).status_code == 200  # the save goes through now
    month = AccountingPeriod.objects.get(workspace=workspace, start_date__lte=first.start_date, end_date__gte=first.start_date)
    month.status = "closed"
    month.save()
    closed = post(first.start_date)
    assert closed.data["code"] == "period_closed"
    assert "reopened" in api.post(f"/api/v1/w/{workspace.slug}/periods/open-for-date/", {"date": first.start_date.isoformat()}, format="json").data["message"]
    assert post(first.start_date).status_code == 200
