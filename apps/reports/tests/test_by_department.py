from datetime import date
from decimal import Decimal as D

import pytest

from apps.invoices.tests.test_sales_flow import url

pytestmark = pytest.mark.django_db


@pytest.fixture
def split_books(workspace, owner):
    """Sales of 1,000 in Shop (tagged by department), rent of 300 in Office (through its cost centre), 50 untagged."""
    from apps.costcenters.models import CostCenter
    from apps.departments.models import Department
    from apps.journals.services import LineInput, post_lines
    from apps.ledgeraccounts.services import system_account

    shop = Department.objects.create(workspace=workspace, name="Shop")
    office = Department.objects.create(workspace=workspace, name="Office")
    office_cc = CostCenter.objects.create(workspace=workspace, code="CC-OFF", name="Office costs", department=office)
    bank, sales, rent = system_account(workspace, "bank"), system_account(workspace, "sales"), system_account(workspace, "cogs")
    on = date.today().replace(day=1)

    def post(lines):
        post_lines(workspace, entry_date=on, description="test", lines=lines, source="manual", dimensions=(None, None))

    post([LineInput(account=bank, debit=D("1000")), LineInput(account=sales, credit=D("1000"), department=shop)])
    post([LineInput(account=rent, debit=D("300"), cost_center=office_cc), LineInput(account=bank, credit=D("300"))])
    post([LineInput(account=rent, debit=D("50")), LineInput(account=bank, credit=D("50"))])
    return shop, office, office_cc


def test_profit_and_loss_by_department(workspace, owner, client_for, split_books):
    api = client_for(owner)
    data = api.get(url(workspace, "reports/profit-and-loss/by/")).data
    names = [c["name"] for c in data["columns"]]
    assert names == ["Office", "Shop", "Not tagged"], names
    assert [D(v) for v in data["net_profit"]] == [D("-300"), D("1000"), D("-50"), D("650")]  # columns, then the total

    by_cc = api.get(url(workspace, "reports/profit-and-loss/by/"), {"dimension": "cost_center"}).data
    assert [c["name"] for c in by_cc["columns"]] == ["CC-OFF Office costs", "Not tagged"]
    assert api.get(url(workspace, "reports/profit-and-loss/by/"), {"dimension": "colour"}).status_code == 400


def test_someone_limited_to_a_department(workspace, owner, add_member, client_for, split_books):
    from apps.memberships.models import Membership

    shop, office, office_cc = split_books
    clerk = add_member(workspace, "accounts@example.com", "accountant")
    member = Membership.objects.get(workspace=workspace, user=clerk)
    owner_api, api = client_for(owner), client_for(clerk)

    me = Membership.objects.get(workspace=workspace, user=owner)
    assert owner_api.patch(f"/api/v1/w/{workspace.slug}/members/{me.id}/", {"limited_department_id": str(shop.id)}, format="json").status_code == 409
    res = owner_api.patch(f"/api/v1/w/{workspace.slug}/members/{member.id}/", {"limited_department_id": str(office.id)}, format="json")
    assert res.status_code == 200 and res.data["limited_department_name"] == "Office", res.data

    assert api.get(url(workspace, "context/")).data["limited_department"]["name"] == "Office"
    data = api.get(url(workspace, "reports/profit-and-loss/by/")).data
    assert [c["name"] for c in data["columns"]] == ["Office"] and [D(v) for v in data["net_profit"]] == [D("-300"), D("-300")]
    pl = api.get(url(workspace, "reports/profit-and-loss/")).data
    assert D(pl["net_profit"]) == D("-300")
    for path in ("reports/balance-sheet/", "reports/trial-balance/", "reports/vat/", "reports/period/", "journals/"):
        assert api.get(url(workspace, path)).status_code == 403, path

    centres = api.get(url(workspace, "cost-centers/")).data
    rows = centres["results"] if isinstance(centres, dict) else centres
    assert [r["code"] for r in rows] == ["CC-OFF"]
    assert api.patch(f"/api/v1/w/{workspace.slug}/members/{member.id}/", {"limited_department_id": None}, format="json").status_code in (403, 409)


def test_tagged_journal_recharge(workspace, owner, client_for, split_books):
    """A manual journal tagged line by line moves cost from one department to another (an internal recharge)."""
    from apps.ledgeraccounts.services import system_account

    shop, office, office_cc = split_books
    from apps.costcenters.models import CostCenter

    shop_cc = CostCenter.objects.create(workspace=workspace, code="CC-SHOP", name="Shop", department=shop)
    api = client_for(owner)
    cost, income = system_account(workspace, "cogs"), system_account(workspace, "sales")
    on = date.today().replace(day=1).isoformat()
    entry = api.post(url(workspace, "journals/"), {"entry_date": on, "description": "Office services to Shop", "lines": [
        {"account_id": str(cost.id), "debit": "100", "credit": "0", "cost_center_id": str(shop_cc.id)},
        {"account_id": str(income.id), "debit": "0", "credit": "100", "cost_center_id": str(office_cc.id)},
    ]}, format="json")
    assert entry.status_code == 201, entry.data
    assert [str(ln["cost_center_id"]) for ln in entry.data["lines"]] == [str(shop_cc.id), str(office_cc.id)]
    assert api.post(url(workspace, f"journals/{entry.data['id']}/post/")).status_code == 200
    data = api.get(url(workspace, "reports/profit-and-loss/by/")).data
    net = dict(zip([c["name"] for c in data["columns"]], [D(v) for v in data["net_profit"]], strict=False))
    assert net["Office"] == D("-200") and net["Shop"] == D("900")  # -300 + 100 charged out; 1000 - 100 charged in
    assert D(data["net_profit"][-1]) == D("650")  # the company total doesn't move
