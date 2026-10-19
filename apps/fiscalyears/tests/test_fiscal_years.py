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
