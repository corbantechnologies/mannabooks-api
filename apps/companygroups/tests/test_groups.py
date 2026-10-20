from decimal import Decimal as D

import pytest

from apps.invoices.tests.test_sales_flow import url

pytestmark = pytest.mark.django_db


@pytest.fixture
def setup(workspace, owner, client_for):
    """Acme Traders and Acme Transport, both the owner's, both in KES."""
    from apps.periods.models import AccountingPeriod
    from apps.workspaces.services import create_workspace

    transport = create_workspace(owner, name="Acme Transport", currency="KES")
    day = AccountingPeriod.objects.filter(workspace=workspace).order_by("start_date").first().start_date.isoformat()
    return {"api": client_for(owner), "traders": workspace, "transport": transport, "day": day}


def account(ws, code):
    from apps.ledgeraccounts.models import LedgerAccount

    return str(LedgerAccount.objects.get(workspace=ws, code=code).id)


def test_group_intercompany_and_consolidation(setup, make_user, client_for, add_member):
    api, traders, transport, day = setup["api"], setup["traders"], setup["transport"], setup["day"]
    group = api.post("/api/v1/groups/", {"name": "Acme Group", "currency": "KES"}, format="json")
    assert group.status_code == 201 and group.data["is_owner"]
    gid = group.data["id"]
    for ws in (traders, transport):
        assert api.post(f"/api/v1/groups/{gid}/companies/", {"workspace": ws.slug}, format="json").status_code == 200
    assert [c["name"] for c in api.get(f"/api/v1/groups/{gid}/").data["companies"]] == ["Acme Traders", "Acme Transport"]
    assert api.get(url(traders, "")).data["group_name"] == "Acme Group"

    ic = f"/api/v1/groups/{gid}/intercompany/"
    wrong = api.post(ic, {"kind": "sale", "from_workspace": traders.slug, "to_workspace": transport.slug, "transaction_date": day,
                          "description": "Delivery recharge", "amount": "10000", "from_account_id": account(traders, "1100"),
                          "to_account_id": account(transport, "6040")}, format="json")
    assert wrong.status_code == 409  # a sale needs the seller's income account
    sale = api.post(ic, {"kind": "sale", "from_workspace": traders.slug, "to_workspace": transport.slug, "transaction_date": day,
                         "description": "Delivery recharge", "amount": "10000", "from_account_id": account(traders, "4100"),
                         "to_account_id": account(transport, "6040")}, format="json")
    assert sale.status_code == 201 and sale.data["number"] == "IC-0001", sale.data
    api.post(ic, {"kind": "loan", "from_workspace": traders.slug, "to_workspace": transport.slug, "transaction_date": day,
                  "description": "Loan for a truck deposit", "amount": "20000", "from_account_id": account(traders, "1100"),
                  "to_account_id": account(transport, "1100")}, format="json")
    paid = api.post(ic, {"kind": "settlement", "from_workspace": transport.slug, "to_workspace": traders.slug, "transaction_date": day,
                         "description": "Part repayment", "amount": "10000", "from_account_id": account(transport, "1100"),
                         "to_account_id": account(traders, "1100")}, format="json")
    assert paid.status_code == 201
    balances = api.get(f"{ic}balances/").data
    assert balances == [{"owes": "Acme Transport", "to": "Acme Traders", "amount": "20000.00"}]

    # an outside sale, so the group has real income left after eliminations
    from apps.ledgeraccounts.models import LedgerAccount

    cash = str(LedgerAccount.objects.get(workspace=traders, system_key="cash").id)
    assert api.post(url(traders, "receipts/"), {"issue_date": day, "method": "cash", "deposit_account_id": cash,
                                                "lines": [{"description": "Cement", "quantity": "1", "unit_price": "5000"}]},
                    format="json").status_code == 201

    pl = api.get(f"/api/v1/groups/{gid}/reports/profit-and-loss/", {"from": day, "to": day}).data
    income = {s["key"]: s for s in pl["sections"]}["income"]
    service = next(r for r in income["rows"] if r["code"] == "4100")
    assert service["amounts"] == ["10000.00", "0.00"] and service["eliminations"] == "10000.00" and service["total"] == "0.00"
    assert pl["company_net_profit"] == ["15000.00", "-10000.00"] and pl["net_profit"] == "5000.00"

    bs = api.get(f"/api/v1/groups/{gid}/reports/balance-sheet/", {"as_of": day}).data
    assert bs["balanced"] and bs["intercompany_difference"] == "0.00"
    current = {s["key"]: s for s in bs["groups"]}["current_assets"]
    due = next(r for r in current["rows"] if r["code"] == "1460")
    assert due["amounts"] == ["20000.00", "0.00"] and due["total"] == "0.00"

    voided = api.post(f"{ic}{paid.data['id']}/void/", {"reason": "Entered twice"}, format="json")
    assert voided.status_code == 200 and voided.data["status"] == "void"
    assert api.get(f"{ic}balances/").data[0]["amount"] == "30000.00"

    # someone who sees only one company's reports can see the group but not its consolidated reports
    clerk = client_for(add_member(traders, "acc@example.com", "accountant"))
    assert clerk.get(f"/api/v1/groups/{gid}/").status_code == 200
    assert clerk.get(f"/api/v1/groups/{gid}/reports/profit-and-loss/").status_code == 403
    assert clerk.post(f"/api/v1/groups/{gid}/companies/", {"workspace": traders.slug}, format="json").status_code == 409  # not the owner
    stranger = client_for(make_user(email="x@example.com"))
    assert stranger.get(f"/api/v1/groups/{gid}/").status_code == 404
    assert api.delete(f"/api/v1/groups/{gid}/companies/{transport.slug}/").status_code == 409  # has transactions
    assert D(bs["total_assets"]) > 0
