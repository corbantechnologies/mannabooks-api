from decimal import Decimal as D

import pytest

from apps.invoices.tests.test_sales_flow import tb, url

pytestmark = pytest.mark.django_db


@pytest.fixture
def api(workspace, owner, client_for):
    return client_for(owner)


def membership_of(ws, user):
    from apps.memberships.models import Membership

    return str(Membership.objects.get(workspace=ws, user=user).id)


@pytest.fixture
def ws(workspace):
    return workspace


def test_kenyan_statutory_maths():
    from apps.statutoryrates.models import StatutoryRate
    from apps.statutoryrates.services import BANDS, compute

    rate = StatutoryRate(paye_bands=BANDS, personal_relief=D("2400"), shif_rate=D("2.75"), shif_minimum=D("300"), nssf_rate=D("6"),
                         nssf_lower_limit=D("8000"), nssf_upper_limit=D("72000"), housing_levy_rate=D("1.5"), deductions_before_paye=True)
    r = compute(rate, gross=D("50000"), taxable_earnings=D("50000"))
    assert r["nssf_employee"] == D("3000.00") and r["shif"] == D("1375.00") and r["housing_levy_employee"] == D("750.00")
    assert r["taxable_pay"] == D("44875.00")
    # 24,000 x 10% + 8,333 x 25% + 12,542 x 30% = 2,400 + 2,083.25 + 3,762.60 = 8,245.85; less relief 2,400
    assert r["paye_before_relief"] == D("8245.85") and r["paye"] == D("5845.85")
    low = compute(rate, gross=D("10000"), taxable_earnings=D("10000"))
    assert low["paye"] == D("0.00") and low["shif"] == D("300.00")  # minimum SHIF
    high = compute(rate, gross=D("200000"), taxable_earnings=D("200000"))
    assert high["nssf_employee"] == D("4320.00")  # capped at the upper earnings limit


def test_leave_requests_and_balances(api, ws, add_member, client_for):
    boss = api.post(url(ws, "employees/"), {"first_name": "Grace", "last_name": "Wanjiru"}, format="json").data
    member = add_member(ws, "otieno@example.com", "self-service")
    me = api.post(url(ws, "employees/"), {"first_name": "Peter", "last_name": "Otieno", "reports_to_id": boss["id"], "membership_id": membership_of(ws, member),
                                          "annual_leave_days": "21"}, format="json").data
    assert me["annual_leave_days"] == "21.0"
    peter = client_for(member)
    req = peter.post(url(ws, "leave-requests/"), {"leave_type": "annual", "start_date": "2026-11-02", "end_date": "2026-11-13"}, format="json")
    assert req.status_code == 201, req.data
    assert req.data["days"] == "10.0" and req.data["employee_name"] == "Peter Otieno"  # two working weeks
    assert peter.post(url(ws, "leave-requests/"), {"leave_type": "sick", "start_date": "2026-11-10", "end_date": "2026-11-10"}, format="json").status_code == 409
    assert peter.post(url(ws, f"leave-requests/{req.data['id']}/action/"), {"action": "approve"}, format="json").status_code == 409  # not their own
    bal = peter.get(url(ws, "leave-requests/balances/"), {"year": 2026}).data[0]
    assert bal["pending"] == "10.0" and bal["remaining"] == "11.0"
    ok = api.post(url(ws, f"leave-requests/{req.data['id']}/action/"), {"action": "approve", "note": "Enjoy"}, format="json")
    assert ok.data["status"] == "approved"
    too_much = peter.post(url(ws, "leave-requests/"), {"leave_type": "annual", "start_date": "2026-12-01", "end_date": "2026-12-31"}, format="json")
    assert too_much.status_code == 409  # 23 days asked, 11 left
    assert peter.get(url(ws, "employees/")).data["count"] == 1  # self-service sees only themself


def test_payroll_run_posting_and_payment(api, ws, add_member, client_for):
    from apps.bankaccounts.services import sync

    alice = api.post(url(ws, "employees/"), {"first_name": "Alice", "last_name": "Mumbi", "on_payroll": True, "basic_salary": "50000",
                                             "pay_method": "bank", "bank_name": "KCB", "bank_account_number": "11223344",
                                             "recurring_items": [{"name": "Transport", "kind": "earning", "amount": 5000, "taxable": True},
                                                                 {"name": "SACCO", "kind": "deduction", "amount": 2000}]}, format="json")
    assert alice.status_code == 201, alice.data
    api.post(url(ws, "employees/"), {"first_name": "Brian", "last_name": "Kip", "on_payroll": True, "basic_salary": "20000", "pay_method": "mpesa",
                                     "mpesa_phone": "0712345678"}, format="json")
    api.post(url(ws, "employees/"), {"first_name": "Casual", "last_name": "Worker"}, format="json")  # not on payroll
    from apps.periods.models import AccountingPeriod

    period = AccountingPeriod.objects.filter(workspace=ws).order_by("start_date").first()
    run = api.post(url(ws, "pay-runs/"), {"year": period.start_date.year, "month": period.start_date.month}, format="json")
    assert run.status_code == 201, run.data
    assert run.data["employees"] == 2 and run.data["gross_pay"] == "75000.00"
    slips = api.get(url(ws, "payslips/"), {"pay_run": run.data["id"]}).data["results"]
    a = next(s for s in slips if s["employee_name"] == "Alice Mumbi")
    assert a["gross_pay"] == "55000.00" and a["other_deductions"] == "2000.00" and a["pay_to"] == "KCB 11223344"
    b = next(s for s in slips if s["employee_name"] == "Brian Kip")
    patched = api.patch(url(ws, f"payslips/{b['id']}/"), {"items": [{"name": "Overtime", "kind": "earning", "amount": "3000"}]}, format="json")
    assert patched.data["gross_pay"] == "23000.00"
    assert api.post(url(ws, f"pay-runs/{run.data['id']}/action/"), {"action": "approve"}, format="json").data["status"] == "approved"
    day = run.data["pay_date"]
    rows = tb(ws, day)
    r = api.get(url(ws, f"pay-runs/{run.data['id']}/")).data
    assert rows["6000"]["debit"] == D(r["employer_cost"])
    assert rows["2120"]["credit"] == D(r["total_paye"]) and rows["2200"]["credit"] == D(r["net_pay"]) and rows["2210"]["credit"] == D("2000.00")
    assert api.patch(url(ws, f"payslips/{b['id']}/"), {"basic_salary": "1"}, format="json").status_code == 409
    sync(ws)
    bank = next(x for x in api.get(url(ws, "bank-accounts/")).data["results"] if x["name"] == "Bank account")
    paid = api.post(url(ws, f"pay-runs/{run.data['id']}/action/"), {"action": "pay", "bank_account_id": bank["id"], "date": day}, format="json")
    assert paid.data["status"] == "paid"
    remit = api.post(url(ws, f"pay-runs/{run.data['id']}/action/"), {"action": "remit", "kind": "paye", "bank_account_id": bank["id"], "date": day,
                                                                      "reference": "KRA-PRN-1"}, format="json")
    assert "paye" in remit.data["remittances"]
    rows = tb(ws, day)
    assert "2200" not in rows and "2120" not in rows
    # an employee with a login sees their own payslip once approved
    member = add_member(ws, "brian@example.com", "self-service")
    api.patch(url(ws, f"employees/{b['employee']}/"), {"membership_id": membership_of(ws, member)}, format="json")
    mine = client_for(member).get(url(ws, "payslips/")).data["results"]
    assert [s["employee_name"] for s in mine] == ["Brian Kip"] and mine[0]["net_pay"] == patched.data["net_pay"]
    assert client_for(member).get(url(ws, f"employees/{alice.data['id']}/")).status_code == 404  # can't see colleagues
