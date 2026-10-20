import pytest

from apps.invoices.tests.test_sales_flow import customer, url, vat16

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


def test_quotation_invoice_payment_chain(api, ws, day):
    cust = customer(api, ws)
    quote = api.post(url(ws, "quotations/"), {"customer_id": cust["id"], "issue_date": day,
                                              "lines": [{"description": "Cement", "quantity": "2", "unit_price": "500", "tax_rate_id": vat16(ws)}]},
                     format="json").data
    inv = {"id": api.post(url(ws, f"quotations/{quote['id']}/convert/")).data["invoice_id"]}
    api.post(url(ws, f"invoices/{inv['id']}/issue/"))
    cash = next(a for a in api.get(url(ws, "ledger-accounts/")).data if a["code"] == "1000")
    paid = api.post(url(ws, "payments/"), {"customer_id": cust["id"], "payment_date": day, "amount": "1160", "method": "cash",
                                           "deposit_account_id": cash["id"], "allocations": [{"invoice_id": inv["id"], "amount": "1160"}]}, format="json")
    assert paid.status_code == 201, paid.data
    chain = api.get(url(ws, "related-documents/"), {"kind": "quotation", "id": quote["id"]}).data
    assert [r["kind"] for r in chain] == ["quotation", "invoice", "payment"]
    assert chain[0]["current"] and not chain[1]["current"]
    from_payment = api.get(url(ws, "related-documents/"), {"kind": "payment", "id": paid.data["id"]}).data
    assert {r["kind"] for r in from_payment} == {"quotation", "invoice", "payment"}  # the same chain from the other end
