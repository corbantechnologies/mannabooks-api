import pytest

from apps.bills.tests.test_purchasing_and_stock import api, day, ws  # noqa: F401
from apps.invoices.tests.test_sales_flow import url

pytestmark = pytest.mark.django_db


def test_lead_to_customer_deal_and_won_quotation(api, ws, day, add_member, client_for):  # noqa: F811
    no_contact = api.post(url(ws, "leads/"), {"name": "Jane Wanjiku"}, format="json")
    assert no_contact.status_code == 400 and "phone" in no_contact.data["errors"]
    lead = api.post(url(ws, "leads/"), {"name": "Jane Wanjiku", "company": "Wanjiku Builders", "phone": "0722000111", "source": "referral",
                                        "interest": "Cement for a 4-storey block", "estimated_value": "250000"}, format="json")
    assert lead.status_code == 201 and lead.data["number"] == "LD-0001" and lead.data["status"] == "new"
    lead = lead.data
    task = api.post(url(ws, "activities/"), {"kind": "call", "subject": "Call Jane about delivery dates", "lead_id": lead["id"],
                                             "due_at": "2020-01-01T09:00:00Z"}, format="json")
    assert task.status_code == 201 and task.data["overdue"] and not task.data["done"] and task.data["assigned_to_name"] == "Owner Person"
    assert api.get(url(ws, "activities/"), {"mine": "true", "overdue": "true"}).data["count"] == 1
    assert api.get(url(ws, f"leads/{lead['id']}/")).data["open_tasks"] == 1
    assert api.patch(url(ws, f"leads/{lead['id']}/"), {"status": "converted"}, format="json").status_code == 400  # only through Convert

    converted = api.post(url(ws, f"leads/{lead['id']}/action/"), {"action": "convert", "deal_title": "Cement for Ruaka block"}, format="json")
    assert converted.status_code == 200, converted.data
    assert converted.data["status"] == "converted" and converted.data["customer_name"] == "Wanjiku Builders"
    customer_id = converted.data["customer_id"]
    deals = api.get(url(ws, "deals/"), {"lead": lead["id"]}).data["results"]
    assert len(deals) == 1 and deals[0]["stage"] == "qualified" and deals[0]["value"] == "250000.00" and deals[0]["weighted_value"] == "62500.00"
    deal = deals[0]
    assert api.get(url(ws, "activities/"), {"customer": customer_id}).data["count"] == 1  # the call moved with the lead

    lost = api.post(url(ws, f"deals/{deal['id']}/move/"), {"stage": "lost"}, format="json")
    assert lost.status_code == 409  # needs a reason
    from apps.taxrates.models import TaxRate

    quote = api.post(url(ws, "quotations/"), {"customer_id": customer_id, "issue_date": day, "lines": [
        {"description": "Cement 50kg", "quantity": "200", "unit_price": "1000", "tax_rate_id": str(TaxRate.objects.get(workspace=ws, code="VAT16").id)}]},
        format="json").data
    linked = api.patch(url(ws, f"deals/{deal['id']}/"), {"quotation_id": quote["id"]}, format="json")
    assert linked.status_code == 200 and linked.data["stage"] == "proposal" and linked.data["quotation_number"] == quote["number"]
    assert api.post(url(ws, f"quotations/{quote['id']}/convert/")).status_code in (200, 201)
    won = api.get(url(ws, f"deals/{deal['id']}/")).data
    assert won["stage"] == "won" and won["closed_at"]

    pipeline = api.get(url(ws, "deals/pipeline/")).data
    stages = {s["stage"]: s for s in pipeline["stages"]}
    assert stages["won"]["count"] == 1 and pipeline["won_this_month"] == "250000.00" and pipeline["win_rate"] == "100.0"

    done = api.patch(url(ws, f"activities/{task.data['id']}/"), {"done": True}, format="json")
    assert done.data["done"] and done.data["done_at"]
    accountant = client_for(add_member(ws, "acc@example.com", "accountant"))
    assert accountant.get(url(ws, "leads/")).status_code == 200
    assert accountant.post(url(ws, "leads/"), {"name": "X", "phone": "1"}, format="json").status_code == 403  # view only
