import pytest

from apps.bills.tests.test_purchasing_and_stock import api, day, ws  # noqa: F401
from apps.invoices.tests.test_sales_flow import customer, url, vat16

pytestmark = pytest.mark.django_db


@pytest.fixture
def buyer(make_user, client_for):
    """Another business on MannaBooks: the customer Baraka Supplies Ltd (KRA PIN P000111222Q), not registered for VAT."""
    from apps.workspaces.services import create_workspace

    user = make_user(email="baraka@example.com", full_name="Baraka Owner")
    workspace = create_workspace(user, name="Baraka Supplies Ltd", currency="KES")
    workspace.kra_pin = "P000111222Q"
    workspace.save()
    return workspace, client_for(user)


def test_invoice_becomes_their_bill_and_their_lpo_becomes_our_invoice(api, ws, day, buyer):  # noqa: F811
    from apps.ledgeraccounts.models import LedgerAccount

    them, their_api = buyer
    cust = customer(api, ws)  # has Baraka's KRA PIN
    inv = api.post(url(ws, "invoices/"), {"customer_id": cust["id"], "issue_date": day,
                                          "lines": [{"description": "Cement 50kg", "quantity": "2", "unit_price": "500", "tax_rate_id": vat16(ws)}]},
                   format="json").data
    early = api.post(url(ws, "inbox/send/"), {"kind": "invoice", "document_id": inv["id"]}, format="json")
    assert early.status_code == 409  # a draft can't be sent
    api.post(url(ws, f"invoices/{inv['id']}/issue/"))
    preview = api.get(url(ws, "inbox/preview/"), {"kind": "invoice", "document_id": inv["id"]}).data
    assert preview["available"] and preview["recipient_name"] == "Baraka Supplies Ltd" and preview["last_status"] is None
    sent = api.post(url(ws, "inbox/send/"), {"kind": "invoice", "document_id": inv["id"], "message": "Thanks for your order"}, format="json")
    assert sent.status_code == 201, sent.data
    assert api.post(url(ws, "inbox/send/"), {"kind": "invoice", "document_id": inv["id"]}, format="json").status_code == 409  # already there

    assert their_api.get(f"/api/v1/w/{them.slug}/context/").data["inbox_new"] == 1
    inbox = their_api.get(url(them, "inbox/")).data["results"]
    assert len(inbox) == 1 and inbox[0]["sender_name"] == "Acme Traders" and inbox[0]["total"] == "1160.00"
    msg = inbox[0]
    assert their_api.post(url(them, f"inbox/{msg['id']}/accept/"), {}, format="json").status_code == 409  # which account?
    stock_costs = str(LedgerAccount.objects.get(workspace=them, system_key="cogs").id)
    accepted = their_api.post(url(them, f"inbox/{msg['id']}/accept/"), {"account_id": stock_costs}, format="json")
    assert accepted.status_code == 200, accepted.data
    assert accepted.data["status"] == "accepted" and accepted.data["created_type"] == "bill"
    bill = their_api.get(url(them, f"bills/{accepted.data['created_id']}/")).data
    # they aren't registered for VAT, so the VAT is part of what the cement cost them
    assert bill["status"] == "draft" and bill["supplier_invoice_number"] == msg["number"] == "INV-2026-0001" and bill["total"] == "1160.00"
    assert their_api.get(f"/api/v1/w/{them.slug}/context/").data["inbox_new"] == 0
    assert api.get(url(ws, "inbox/sent/")).data["results"][0]["status"] == "accepted"

    # they order more from us on an LPO; it arrives as a draft invoice for them as our customer
    supplier_id = bill["supplier_id"]
    po = their_api.post(url(them, "purchase-orders/"), {"supplier_id": supplier_id, "order_date": day,
                                                         "lines": [{"description": "Cement 50kg", "quantity": "10", "unit_cost": "580"}]}, format="json").data
    their_api.post(url(them, f"purchase-orders/{po['id']}/action/"), {"action": "approve"}, format="json")
    assert their_api.post(url(them, "inbox/send/"), {"kind": "purchase_order", "document_id": po["id"]}, format="json").status_code == 201
    lpo = api.get(url(ws, "inbox/"), {"kind": "purchase_order"}).data["results"][0]
    made = api.post(url(ws, f"inbox/{lpo['id']}/accept/"), {}, format="json")
    assert made.status_code == 200 and made.data["created_type"] == "invoice", made.data
    draft = api.get(url(ws, f"invoices/{made.data['created_id']}/")).data
    assert draft["status"] == "draft" and str(draft["customer_id"]) == str(cust["id"]) and draft["reference"] == po["number"]


def test_decline_and_not_on_mannabooks(api, ws, day, buyer):  # noqa: F811
    them, their_api = buyer
    cust = customer(api, ws)
    quote = api.post(url(ws, "quotations/"), {"customer_id": cust["id"], "issue_date": day,
                                              "lines": [{"description": "Paint 20l", "quantity": "1", "unit_price": "9000"}]}, format="json").data
    api.post(url(ws, f"quotations/{quote['id']}/status/"), {"action": "send"}, format="json")
    assert api.post(url(ws, "inbox/send/"), {"kind": "quotation", "document_id": quote["id"]}, format="json").status_code == 201
    msg = their_api.get(url(them, "inbox/")).data["results"][0]
    assert their_api.post(url(them, f"inbox/{msg['id']}/decline/"), {"reason": " "}, format="json").status_code in (400, 409)
    declined = their_api.post(url(them, f"inbox/{msg['id']}/decline/"), {"reason": "Found it cheaper"}, format="json")
    assert declined.data["status"] == "declined"
    assert api.get(url(ws, "inbox/sent/")).data["results"][0]["decline_reason"] == "Found it cheaper"
    assert api.post(url(ws, "inbox/send/"), {"kind": "quotation", "document_id": quote["id"]}, format="json").status_code == 201  # can resend

    other = customer(api, ws, name="Walk-in Hardware", kra_pin="A000999888Z")
    quote2 = api.post(url(ws, "quotations/"), {"customer_id": other["id"], "issue_date": day,
                                               "lines": [{"description": "Paint", "quantity": "1", "unit_price": "100"}]}, format="json").data
    api.post(url(ws, f"quotations/{quote2['id']}/status/"), {"action": "send"}, format="json")
    assert not api.get(url(ws, "inbox/preview/"), {"kind": "quotation", "document_id": quote2["id"]}).data["available"]
    nope = api.post(url(ws, "inbox/send/"), {"kind": "quotation", "document_id": quote2["id"]}, format="json")
    assert nope.status_code == 409 and "isn't on MannaBooks" in nope.data["message"]
    assert their_api.get(url(them, f"inbox/{msg['id']}/")).status_code == 200
    assert api.get(url(ws, f"inbox/{msg['id']}/")).status_code == 404  # the sender reads it from Sent, not the recipient's inbox
