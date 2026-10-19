import pytest

from apps.fiscalyears.models import FiscalYear
from apps.ledgeraccounts.models import LedgerAccount

pytestmark = pytest.mark.django_db


def test_opening_balances_post_with_equity_difference(workspace, owner, client_for):
    api = client_for(owner)
    url = f"/api/v1/w/{workspace.slug}/opening-balances/"
    blank = api.get(url).data
    first = FiscalYear.objects.get(workspace=workspace)
    assert blank["status"] == "draft" and blank["lines"] == []
    day = first.start_date.isoformat()  # an open period must cover the date
    bank = LedgerAccount.objects.get(workspace=workspace, code="1100")
    loan = LedgerAccount.objects.get(workspace=workspace, code="2500")
    saved = api.put(url, {"as_of_date": day, "notes": "", "lines": [
        {"account_id": str(bank.id), "debit": "50000", "credit": "0"},
        {"account_id": str(loan.id), "debit": "0", "credit": "20000"},
    ]}, format="json")
    assert saved.status_code == 200 and saved.data["total_debit"] == "50000.00"
    posted = api.post(f"{url}post/")
    assert posted.status_code == 200 and posted.data["status"] == "posted" and posted.data["journal_number"]
    tb = api.get(f"/api/v1/w/{workspace.slug}/reports/trial-balance/", {"as_of": day}).data
    rows = {r["code"]: r for r in tb["rows"]}
    assert rows["3200"]["credit"] == "30000.00" and tb["balanced"]
    assert api.put(url, {"as_of_date": day, "lines": []}, format="json").status_code == 409
    assert api.post(f"{url}unpost/").data["status"] == "draft"
    assert api.get(f"/api/v1/w/{workspace.slug}/reports/trial-balance/", {"as_of": day}).data["rows"] == []
