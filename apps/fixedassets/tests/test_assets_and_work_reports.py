from datetime import date, timedelta
from decimal import Decimal as D

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from apps.invoices.tests.test_sales_flow import tb, url

pytestmark = pytest.mark.django_db


@pytest.fixture
def ws(workspace):
    return workspace


@pytest.fixture
def api(ws, owner, client_for):
    return client_for(owner)


@pytest.fixture(autouse=True)
def media(settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path


def code_id(ws, code):
    from apps.ledgeraccounts.models import LedgerAccount

    return str(LedgerAccount.objects.get(workspace=ws, code=code).id)


def test_depreciation_runs_and_disposal(api, ws):
    laptop = api.post(url(ws, "fixed-assets/"), {"name": "Dell laptops x3", "category": "computers", "purchase_date": "2026-01-15",
                                                 "cost": "120000"}, format="json")
    assert laptop.status_code == 201, laptop.data
    a = laptop.data
    assert a["number"] == "FA-0001" and a["method"] == "straight_line" and a["useful_life_months"] == 36 and a["asset_account_name"] == "Computers and equipment"
    van = api.post(url(ws, "fixed-assets/"), {"name": "Isuzu NKR KDA 123A", "category": "motor_vehicles", "purchase_date": "2022-03-01",
                                              "cost": "2000000", "acquisition": "existing", "opening_accumulated": "500000",
                                              "depreciated_to": "2025-12-31"}, format="json")
    assert van.status_code == 201, van.data
    v = van.data
    assert v["method"] == "reducing_balance" and v["rate_percent"] == "25.00" and v["book_value"] == "1500000.00"
    rows = tb(ws, "2026-01-31")
    assert rows["1510"]["debit"] == D("2000000.00") and rows["1590"]["credit"] == D("500000.00")  # brought in against opening equity
    prev = api.get(url(ws, "depreciation/preview/"), {"month": "2026-01-20"}).data
    assert {p["number"]: p["amount"] for p in prev} == {"FA-0001": "3333.33", "FA-0002": "31250.00"}
    assert api.post(url(ws, "depreciation/run/"), {"month": "2026-01-31"}, format="json").data["total"] == "34583.33"
    run2 = api.post(url(ws, "depreciation/run/"), {"month": "2026-03-15"}, format="json").data
    assert run2["entries"] == 4  # February and March for both
    rows = tb(ws, "2026-03-31")
    # van: 31,250 + 30,598.96 + 29,961.48; laptops 3 x 3,333.33
    assert rows["6120"]["debit"] == D("91810.44") + D("9999.99")
    assert api.post(url(ws, "depreciation/run/"), {"month": "2026-02-28"}, format="json").status_code == 409  # a later month is in
    assert api.post(url(ws, "depreciation/undo/"), {"month": "2026-01-31"}, format="json").status_code == 409  # undo March first
    assert api.post(url(ws, "depreciation/undo/"), {"month": "2026-03-31"}, format="json").status_code == 204
    assert api.get(url(ws, f"fixed-assets/{a['id']}/")).data["depreciated_to"] == "2026-01-31"
    runs = api.get(url(ws, "depreciation/")).data
    assert [r["run_month"] for r in runs] == ["2026-01-31"]
    # selling before February and March are depreciated is refused
    bank = next(r for r in api.get(url(ws, "bank-accounts/")).data["results"] if r["name"] == "Bank account")
    sell = {"action": "dispose", "date": "2026-04-10", "proceeds": "100000", "received_into_id": bank["id"]}
    assert api.post(url(ws, f"fixed-assets/{a['id']}/action/"), sell, format="json").status_code == 409
    api.post(url(ws, "depreciation/run/"), {"month": "2026-03-31"}, format="json")
    sold = api.post(url(ws, f"fixed-assets/{a['id']}/action/"), sell, format="json")
    assert sold.status_code == 200 and sold.data["status"] == "disposed" and sold.data["disposal_gain"] == "-10000.01"
    rows = tb(ws, "2026-04-30")
    assert rows["4550"]["debit"] == D("10000.01")  # loss: book value 110,000.01, sold for 100,000
    assert rows["1520"]["credit"] == D("120000.00")  # cost taken out (this test never posted the purchase bill)
    sched = api.get(url(ws, f"fixed-assets/{v['id']}/schedule/")).data
    assert len(sched["history"]) == 3 and sched["projection"][0]["year"] == 2026
    assert api.patch(url(ws, f"fixed-assets/{v['id']}/"), {"cost": "2100000"}, format="json").status_code == 409  # depreciation charged
    assert api.patch(url(ws, f"fixed-assets/{v['id']}/"), {"serial_number": "KDA 123A"}, format="json").status_code == 200


def _employee(api, ws, user, **extra):
    from apps.memberships.models import Membership

    m = Membership.objects.get(workspace=ws, user=user)
    return api.post(url(ws, "employees/"), {"first_name": user.full_name, "last_name": "X", "membership_id": str(m.id), **extra}, format="json").data


def test_work_reports(api, ws, owner, add_member, client_for):
    from apps.reportsubmissions.services import run_due

    boss_user = add_member(ws, "boss@example.com", "sales")
    staff_user = add_member(ws, "staff@example.com", "self-service")
    other_user = add_member(ws, "other@example.com", "self-service")
    boss = _employee(api, ws, boss_user)
    staff = _employee(api, ws, staff_user, reports_to_id=boss["id"])
    other = _employee(api, ws, other_user)
    b, s = client_for(boss_user), client_for(staff_user)
    assert [p["id"] for p in b.get(url(ws, "report-requests/people/")).data] == [staff["id"]]
    due = date.today() + timedelta(days=3)
    outside = b.post(url(ws, "report-requests/"), {"title": "Weekly sales", "audience": "people", "people_ids": [other["id"]],
                                                   "frequency": "weekly", "first_due_date": due.isoformat()}, format="json")
    assert outside.status_code == 409  # not in their reporting line
    template = SimpleUploadedFile("weekly-template.xlsx", b"template", content_type="application/vnd.ms-excel")
    req = b.post(url(ws, "report-requests/"), {"title": "Weekly sales", "instructions": "Sales by customer and visits made.", "audience": "team",
                                               "frequency": "weekly", "first_due_date": due.isoformat(), "template_file": template}, format="multipart")
    assert req.status_code == 201, req.data
    assert req.data["assignee_names"] == [f"{staff_user.full_name} X"] and req.data["has_template"]
    todo = s.get(url(ws, "report-submissions/")).data["results"]
    assert len(todo) == 1 and todo[0]["can_submit"] and todo[0]["status"] == "pending"
    sub_id = todo[0]["id"]
    assert s.get(url(ws, f"report-requests/{req.data['id']}/template/")).status_code == 200  # the person asked can download it
    assert client_for(other_user).get(url(ws, f"report-submissions/{sub_id}/")).status_code == 404
    assert s.post(url(ws, f"report-submissions/{sub_id}/submit/"), {"body": ""}, format="multipart").status_code == 409  # empty
    upload = SimpleUploadedFile("week42.pdf", b"%PDF-1.4 report", content_type="application/pdf")
    done = s.post(url(ws, f"report-submissions/{sub_id}/submit/"), {"body": "Sold 120 bags.", "file": upload}, format="multipart")
    assert done.status_code == 200 and done.data["status"] == "submitted" and done.data["has_file"]
    review = b.get(url(ws, "report-submissions/"), {"box": "review"}).data["results"]
    assert review[0]["can_review"]
    assert b"".join(b.get(url(ws, f"report-submissions/{sub_id}/file/")).streaming_content) == b"%PDF-1.4 report"
    assert b.post(url(ws, f"report-submissions/{sub_id}/review/"), {"decision": "returned"}, format="json").status_code == 409  # say why
    back = b.post(url(ws, f"report-submissions/{sub_id}/review/"), {"decision": "returned", "comment": "Add the visits"}, format="json")
    assert back.data["status"] == "returned"
    s.post(url(ws, f"report-submissions/{sub_id}/submit/"), {"body": "Sold 120 bags. Visited 14 shops."}, format="multipart")
    ok = b.post(url(ws, f"report-submissions/{sub_id}/review/"), {"decision": "accepted"}, format="json")
    assert ok.data["status"] == "accepted" and ok.data["file_name"] == "week42.pdf"
    result = run_due(due + timedelta(days=1))  # the week has passed: next round opens
    assert result["opened"] == 1
    rounds = s.get(url(ws, "report-submissions/")).data["results"]
    assert sorted(r["due_date"] for r in rounds) == [due.isoformat(), (due + timedelta(days=7)).isoformat()]
    later = run_due(due + timedelta(days=8))
    assert later["late"] == 1 and later["opened"] == 1
