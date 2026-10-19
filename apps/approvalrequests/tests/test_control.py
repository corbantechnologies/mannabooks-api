from decimal import Decimal as D

import pytest

from apps.invoices.tests.test_sales_flow import customer, draft_invoice, url

pytestmark = pytest.mark.django_db


@pytest.fixture
def ws(workspace):
    workspace.vat_registered = True
    workspace.kra_pin = "P051234567X"
    workspace.save()
    return workspace


@pytest.fixture
def api(ws, owner, client_for):
    return client_for(owner)


@pytest.fixture
def day(ws):
    from apps.periods.models import AccountingPeriod

    return AccountingPeriod.objects.filter(workspace=ws).order_by("start_date").first().start_date.isoformat()


def code_id(ws, code):
    from apps.ledgeraccounts.models import LedgerAccount

    return str(LedgerAccount.objects.get(workspace=ws, code=code).id)


def bank(api, ws, name="M-Pesa"):
    return next(r for r in api.get(url(ws, "bank-accounts/")).data["results"] if r["name"] == name)


def spend(api, ws, day, amount, **tags):
    r = api.post(url(ws, "expenses/"), {"expense_date": day, "paid_from_id": bank(api, ws)["id"], "payee": "Rubis", "prices_include_tax": False,
                                        "lines": [{"description": "Fuel", "quantity": "1", "unit_cost": amount, "account_id": code_id(ws, "6040"),
                                                   "tax_rate_id": None}], **tags}, format="json")
    assert r.status_code == 201, r.data
    return r.data


def test_cost_centres_and_projects_tag_the_ledger(api, ws, day):
    van = api.post(url(ws, "cost-centers/"), {"code": "van1", "name": "Delivery van KDA 123A"}, format="json")
    assert van.status_code == 201 and van.data["code"] == "VAN1"
    cust = customer(api, ws)
    job = api.post(url(ws, "projects/"), {"name": "Kitengela warehouse fit-out", "customer_id": cust["id"], "contract_value": "50000",
                                          "cost_budget": "20000"}, format="json")
    assert job.status_code == 201 and job.data["code"] == "PRJ-0001"
    exp = spend(api, ws, day, "3000", cost_center_id=van.data["id"], project_id=job.data["id"])
    assert exp["cost_center_name"] == "Delivery van KDA 123A" and exp["project_name"] == "Kitengela warehouse fit-out"
    from apps.journals.models import JournalLine

    lines = JournalLine.objects.filter(entry__source_id=exp["id"])
    tagged = {line.account.code: (line.cost_center_id, line.project_id) for line in lines}
    assert str(tagged["6040"][0]) == van.data["id"] and str(tagged["6040"][1]) == job.data["id"]
    assert tagged["1150"] == (None, None)  # only income and expense lines carry the tags
    spend(api, ws, day, "1000")  # untagged
    inv = draft_invoice(api, ws, cust, day, price="10000").data
    api.patch(url(ws, f"invoices/{inv['id']}/"), {"project_id": job.data["id"]}, format="json")
    api.post(url(ws, f"invoices/{inv['id']}/issue/"))
    s = api.get(url(ws, f"projects/{job.data['id']}/summary/")).data
    assert D(s["income"]) == D("10000.00") and D(s["costs"]) == D("3000.00") and D(s["profit"]) == D("7000.00")
    assert D(s["budget_used_percent"]) == D("15.00") and D(s["invoiced"]) == D("11600.00")
    pl = api.get(url(ws, "reports/profit-and-loss/"), {"from": day, "to": day, "cost_center": van.data["id"]}).data
    expenses = next(sec for sec in pl["sections"] if sec["key"] == "expense")
    assert D(expenses["total"]) == D("3000.00")  # the untagged 1,000 is left out
    whole = api.get(url(ws, "reports/profit-and-loss/"), {"from": day, "to": day}).data
    assert D(whole["net_profit"]) == D("6000.00")  # 10,000 sales - 4,000 fuel
    assert api.delete(url(ws, f"cost-centers/{van.data['id']}/")).status_code == 409


def test_budget_versus_actual_and_check(api, ws, day):
    from apps.fiscalyears.models import FiscalYear

    year = FiscalYear.objects.filter(workspace=ws).order_by("start_date").first()
    b = api.post(url(ws, "budgets/"), {"name": "Operating budget", "fiscal_year_id": str(year.id),
                                       "lines": [{"account_id": code_id(ws, "6040"), "amounts": ["2000"] * 12}]}, format="json")
    assert b.status_code == 201, b.data
    assert b.data["total_expense"] == "24000.00" and len(b.data["months"]) == 12
    bad = api.patch(url(ws, f"budgets/{b.data['id']}/"), {"lines": [{"account_id": code_id(ws, "1100"), "amounts": ["1"] * 12}]}, format="json")
    assert bad.status_code == 409  # balance-sheet accounts aren't budgeted
    ok = api.post(url(ws, f"budgets/{b.data['id']}/action/"), {"action": "approve"}, format="json")
    assert ok.data["status"] == "approved"
    assert api.patch(url(ws, f"budgets/{b.data['id']}/"), {"notes": "x"}, format="json").status_code == 409
    spend(api, ws, day, "2500")
    va = api.get(url(ws, f"budgets/{b.data['id']}/versus-actual/"), {"through": day}).data
    row = va["rows"][0]
    assert D(row["actual"][0]) == D("2500.00") and D(row["ytd_budget"]) == D("2000.00") and D(row["variance"]) == D("-500.00")
    assert row["favourable"] is False
    chk = api.get(url(ws, "budgets/check/"), {"account": code_id(ws, "6040"), "date": day, "amount": "30000"}).data
    assert chk["budgeted"] and D(chk["remaining"]) == D("21500.00") and chk["would_exceed"] is True


def _employee(api, ws, user, **extra):
    from apps.memberships.models import Membership

    m = Membership.objects.get(workspace=ws, user=user)
    return api.post(url(ws, "employees/"), {"first_name": user.full_name, "last_name": "X", "membership_id": str(m.id), **extra}, format="json").data


def test_multi_level_purchase_order_approval(api, ws, day, add_member, client_for, owner):
    store_user = add_member(ws, "store@example.com", "store-manager")
    boss_user = add_member(ws, "boss@example.com", "accountant")
    boss = _employee(api, ws, boss_user)
    _employee(api, ws, store_user, reports_to_id=boss["id"])
    rule = api.post(url(ws, "approval-rules/"), {"name": "Orders over 5,000", "document_type": "purchase_order", "min_amount": "5000",
                                                 "levels": [{"kind": "supervisor"}, {"kind": "owner"}]}, format="json")
    assert rule.status_code == 201, rule.data
    assert [lvl["label"] for lvl in rule.data["levels"]] == ["Their supervisor", "The owner"]
    store, boss_api = client_for(store_user), client_for(boss_user)
    sup = api.post(url(ws, "suppliers/"), {"name": "Bamburi Cement"}, format="json").data
    small = store.post(url(ws, "purchase-orders/"), {"supplier_id": sup["id"], "order_date": day,
                                                     "lines": [{"description": "Nails", "quantity": "1", "unit_cost": "1000", "account_id": code_id(ws, "6040")}]},
                       format="json").data
    status = store.get(url(ws, "approvals/status/"), {"document_type": "purchase_order", "object_id": small["id"]}).data
    assert status["required"] is False  # below the rule's band
    po = store.post(url(ws, "purchase-orders/"), {"supplier_id": sup["id"], "order_date": day,
                                                  "lines": [{"description": "Cement", "quantity": "10", "unit_cost": "700", "account_id": code_id(ws, "6040")}]},
                    format="json").data
    status = store.get(url(ws, "approvals/status/"), {"document_type": "purchase_order", "object_id": po["id"]}).data
    assert status["required"] and status["can_submit"] and status["levels"] == ["Their supervisor", "The owner"]
    req = store.post(url(ws, "approvals/"), {"document_type": "purchase_order", "object_id": po["id"]}, format="json")
    assert req.status_code == 201 and req.data["waiting_on"] == [boss_user.full_name]
    # the owner can't skip the supervisor's level
    assert api.post(url(ws, f"approvals/{req.data['id']}/decide/"), {"decision": "approved"}, format="json").status_code == 409
    inbox = boss_api.get(url(ws, "approvals/")).data["results"]
    assert [r["id"] for r in inbox] == [req.data["id"]] and inbox[0]["can_decide"]
    step1 = boss_api.post(url(ws, f"approvals/{req.data['id']}/decide/"), {"decision": "approved", "comment": "Needed for the Ruiru job"}, format="json")
    assert step1.status_code == 200 and step1.data["current_level"] == 1 and step1.data["waiting_on"] == [owner.full_name]
    assert api.get(url(ws, f"purchase-orders/{po['id']}/")).data["status"] == "draft"
    final = api.post(url(ws, f"approvals/{req.data['id']}/decide/"), {"decision": "approved"}, format="json")
    assert final.data["status"] == "approved"
    order = api.get(url(ws, f"purchase-orders/{po['id']}/")).data
    assert order["status"] == "approved" and order["approved_by_name"] == owner.full_name
    # a rejection sends it back with a reason
    po2 = store.post(url(ws, "purchase-orders/"), {"supplier_id": sup["id"], "order_date": day,
                                                   "lines": [{"description": "Steel", "quantity": "1", "unit_cost": "9000", "account_id": code_id(ws, "6040")}]},
                     format="json").data
    r2 = store.post(url(ws, "approvals/"), {"document_type": "purchase_order", "object_id": po2["id"]}, format="json").data
    assert boss_api.post(url(ws, f"approvals/{r2['id']}/decide/"), {"decision": "rejected"}, format="json").status_code == 409  # needs a reason
    no = boss_api.post(url(ws, f"approvals/{r2['id']}/decide/"), {"decision": "rejected", "comment": "Get three quotes"}, format="json")
    assert no.data["status"] == "rejected"
    assert store.get(url(ws, "approvals/"), {"box": "mine"}).data["count"] == 2
    # the approve button itself also routes through the chain
    direct = api.post(url(ws, f"purchase-orders/{po2['id']}/action/"), {"action": "approve"}, format="json")
    assert direct.status_code == 200 and direct.data["status"] == "draft"
    pending = api.get(url(ws, "approvals/status/"), {"document_type": "purchase_order", "object_id": po2["id"]}).data
    assert pending["request"]["status"] == "pending" and pending["request"]["waiting_on"] == [boss_user.full_name]


def test_approval_limit_sends_to_module_in_charge(api, ws, day, add_member, client_for):
    from apps.memberships.models import Membership

    clerk = add_member(ws, "clerk@example.com", "accountant")
    head_user = add_member(ws, "head@example.com", "accountant")
    head = _employee(api, ws, head_user)
    api.post(url(ws, "departments/"), {"name": "Finance", "head_id": head["id"], "modules": ["finance"]}, format="json")
    Membership.objects.filter(workspace=ws, user=clerk).update(approval_limit=D("10000"))
    sup = api.post(url(ws, "suppliers/"), {"name": "Kenya Power"}, format="json").data
    bill = api.post(url(ws, "bills/"), {"supplier_id": sup["id"], "bill_date": day, "supplier_invoice_number": "KP-1",
                                        "lines": [{"description": "Power", "quantity": "1", "unit_cost": "25000", "account_id": code_id(ws, "6040")}]},
                    format="json").data
    api.post(url(ws, f"bills/{bill['id']}/post/"), format="json")
    v = api.post(url(ws, "payment-vouchers/"), {"supplier_id": sup["id"], "voucher_date": day, "lines": [{"bill_id": bill["id"], "amount": "25000"}]},
                 format="json").data
    c = client_for(clerk)
    r = c.post(url(ws, f"payment-vouchers/{v['id']}/action/"), {"action": "approve"}, format="json")
    assert r.status_code == 200 and r.data["status"] == "draft"  # above the clerk's limit
    st = c.get(url(ws, "approvals/status/"), {"document_type": "payment_voucher", "object_id": v["id"]}).data
    assert st["request"]["waiting_on"] == [head_user.full_name]
    done = client_for(head_user).post(url(ws, f"approvals/{st['request']['id']}/decide/"), {"decision": "approved"}, format="json")
    assert done.status_code == 200, done.data
    assert api.get(url(ws, f"payment-vouchers/{v['id']}/")).data["status"] == "approved"


def test_financial_statements(api, ws, day):
    cust = customer(api, ws)
    inv = draft_invoice(api, ws, cust, day, price="20000").data
    api.post(url(ws, f"invoices/{inv['id']}/issue/"))
    spend(api, ws, day, "5000")
    pl = api.get(url(ws, "reports/profit-and-loss/"), {"from": day, "to": day, "compare": "previous_year"}).data
    assert D(pl["gross_profit"]) == D("20000.00") and D(pl["net_profit"]) == D("15000.00") and D(pl["compare_net_profit"]) == 0
    bs = api.get(url(ws, "reports/balance-sheet/"), {"as_of": day}).data
    assert bs["balanced"], bs
    assert D(bs["total_assets"]) == D("23200.00") - D("5000.00")  # receivable 23,200 less M-Pesa spent
    aged = api.get(url(ws, "reports/aged/receivables/"), {"as_of": day}).data
    assert D(aged["totals"]["current"]) == D("23200.00") and aged["rows"][0]["name"] == cust["name"]
    assert api.get(url(ws, "reports/aged/nonsense/")).status_code == 404
    vat = api.get(url(ws, "reports/vat/"), {"from": day, "to": day}).data
    assert D(vat["output_vat"]) == D("3200.00") and D(vat["net_vat"]) == D("3200.00")
    assert vat["sales"][0]["tax_rate"] and D(vat["sales"][0]["net"]) == D("20000.00")
