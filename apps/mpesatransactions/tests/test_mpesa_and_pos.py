from decimal import Decimal as D

import pytest

from apps.invoices.tests.test_sales_flow import customer, draft_invoice, tb, url, vat16

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


@pytest.fixture
def connected(api, ws, monkeypatch):
    from apps.mpesaconnections import daraja

    res = api.put(url(ws, "mpesa/connection/"), {"shortcode": "174379", "shortcode_type": "paybill", "consumer_key": "ck",
                                                  "consumer_secret": "cs", "passkey": "pk", "is_active": True}, format="json")
    assert res.status_code == 200 and res.data["has_credentials"] and "passkey" not in res.data
    monkeypatch.setattr(daraja, "stk_push", lambda conn, **kw: {"CheckoutRequestID": "ws_CO_1", "MerchantRequestID": "m1"})
    from apps.mpesaconnections.models import MpesaConnection

    return MpesaConnection.objects.get(workspace=ws)


def stk_callback(token, code=0, amount=1160, receipt="SJK1ABC234"):
    from rest_framework.test import APIClient

    meta = {"Item": [{"Name": "Amount", "Value": amount}, {"Name": "MpesaReceiptNumber", "Value": receipt},
                     {"Name": "TransactionDate", "Value": 20260101101500}, {"Name": "PhoneNumber", "Value": 254712345678}]}
    body = {"Body": {"stkCallback": {"MerchantRequestID": "m1", "CheckoutRequestID": "ws_CO_1", "ResultCode": code,
                                     "ResultDesc": "ok" if code == 0 else "Request cancelled by user", **({"CallbackMetadata": meta} if code == 0 else {})}}}
    return APIClient().post(f"/api/v1/hooks/pay/{token}/stk/", body, format="json")


def test_phone_numbers():
    from apps.core.exceptions import BusinessRuleError
    from apps.mpesatransactions.services import normalise_phone

    assert normalise_phone("0712 345 678") == normalise_phone("+254712345678") == normalise_phone("712345678") == "254712345678"
    assert normalise_phone("0110345678") == "254110345678"
    with pytest.raises(BusinessRuleError):
        normalise_phone("12345")


def test_stk_prompt_pays_an_invoice(api, ws, day, connected):
    cust = customer(api, ws)
    inv = draft_invoice(api, ws, cust, day).data
    api.post(url(ws, f"invoices/{inv['id']}/issue/"))
    assert api.post(url(ws, "mpesa/transactions/prompt/"), {"phone": "0712345678", "amount": "1160.50", "invoice_id": inv["id"]}, format="json").status_code == 409
    tx = api.post(url(ws, "mpesa/transactions/prompt/"), {"phone": "0712345678", "amount": "1160", "invoice_id": inv["id"]}, format="json")
    assert tx.status_code == 201 and tx.data["status"] == "pending" and tx.data["phone"] == "254712345678"
    assert stk_callback(connected.callback_token).data == {"ResultCode": 0, "ResultDesc": "Accepted"}
    stk_callback(connected.callback_token)  # Safaricom repeats callbacks: nothing happens twice
    done = api.get(url(ws, f"mpesa/transactions/{tx.data['id']}/")).data
    assert done["status"] == "completed" and done["mpesa_receipt"] == "SJK1ABC234" and done["payment_number"].startswith("PAY-")
    assert api.get(url(ws, f"invoices/{inv['id']}/")).data["status"] == "paid"
    assert tb(ws, day)["1150"]["debit"] == D("1160.00")


def test_cancelled_prompt(api, ws, connected):
    tx = api.post(url(ws, "mpesa/transactions/prompt/"), {"phone": "0712345678", "amount": "100"}, format="json").data
    stk_callback(connected.callback_token, code=1032)
    assert api.get(url(ws, f"mpesa/transactions/{tx['id']}/")).data["status"] == "cancelled"


def test_paybill_payment_matches_by_invoice_number(api, ws, day, connected):
    from rest_framework.test import APIClient

    cust = customer(api, ws)
    inv = draft_invoice(api, ws, cust, day).data
    inv = api.post(url(ws, f"invoices/{inv['id']}/issue/")).data
    hook = f"/api/v1/hooks/pay/{connected.callback_token}/c2b/"
    assert APIClient().post(hook + "validation/", {}, format="json").data["ResultCode"] == 0
    body = {"TransID": "SJK9XYZ111", "TransAmount": "500.00", "BillRefNumber": inv["number"].lower(), "MSISDN": "254712345678",
            "FirstName": "Jane", "TransTime": "20260101093000"}
    APIClient().post(hook + "confirmation/", body, format="json")
    APIClient().post(hook + "confirmation/", body, format="json")
    assert api.get(url(ws, f"invoices/{inv['id']}/")).data["balance_due"] == "660.00"
    stray = {**body, "TransID": "SJK9XYZ222", "BillRefNumber": "shop", "TransAmount": "300"}
    APIClient().post(hook + "confirmation/", stray, format="json")
    unmatched = api.get(url(ws, "mpesa/transactions/"), {"matched": "false"}).data["results"]
    assert [t["mpesa_receipt"] for t in unmatched] == ["SJK9XYZ222"]
    applied = api.post(url(ws, f"mpesa/transactions/{unmatched[0]['id']}/apply/"), {"customer_id": cust["id"], "invoice_id": inv["id"]}, format="json")
    assert applied.status_code == 200 and applied.data["is_matched"]
    assert api.get(url(ws, f"invoices/{inv['id']}/")).data["balance_due"] == "360.00"
    assert APIClient().post("/api/v1/hooks/pay/wrong-token/stk/", {}, format="json").status_code == 404


def test_pos_shift_sales_and_cash_count(api, ws, day, add_member, client_for):
    reg = api.post(url(ws, "pos/registers/"), {"name": "Till 1"}, format="json")
    assert reg.status_code == 201
    cashier = client_for(add_member(ws, "cashier@example.com", "cashier"))
    assert cashier.post(url(ws, "pos/registers/"), {"name": "Till 2"}, format="json").status_code == 403
    assert cashier.get(url(ws, "pos/shifts/current/")).status_code == 204
    shift = cashier.post(url(ws, "pos/shifts/"), {"register_id": reg.data["id"], "opening_float": "1000"}, format="json")
    assert shift.status_code == 201 and shift.data["number"].startswith("SH-")
    assert api.post(url(ws, "pos/shifts/"), {"register_id": reg.data["id"]}, format="json").status_code == 409
    line = [{"description": "Paint 4L", "quantity": "1", "unit_price": "2320", "tax_rate_id": vat16(ws)}]
    sale = cashier.post(url(ws, "receipts/"), {"issue_date": day, "method": "cash", "shift_id": shift.data["id"], "lines": line,
                                               "prices_include_tax": True}, format="json")
    assert sale.status_code == 201, sale.data
    assert sale.data["deposit_account_name"] == "Cash on hand"
    assert api.post(url(ws, "receipts/"), {"issue_date": day, "method": "cash", "shift_id": shift.data["id"], "lines": line}, format="json").status_code == 409
    card = cashier.post(url(ws, "receipts/"), {"issue_date": day, "method": "card", "shift_id": shift.data["id"], "lines": line,
                                               "prices_include_tax": True}, format="json")
    assert card.data["deposit_account_name"] == "Bank account"
    current = cashier.get(url(ws, "pos/shifts/current/")).data
    assert current["totals"]["sales_count"] == 2 and current["totals"]["expected_cash"] == "3320.00"
    closed = cashier.post(url(ws, f"pos/shifts/{shift.data['id']}/close/"), {"counted_cash": "3300"}, format="json")
    assert closed.data["status"] == "closed" and closed.data["cash_difference"] == "-20.00"
    rows = tb(ws, closed.data["closed_at"][:10])
    assert rows["6910"]["debit"] == D("20.00")
    assert cashier.post(url(ws, "receipts/"), {"issue_date": day, "method": "cash", "shift_id": shift.data["id"], "lines": line}, format="json").status_code == 409


def test_till_sale_paid_by_prompt(api, ws, day, connected):
    reg = api.post(url(ws, "pos/registers/"), {"name": "Till 1"}, format="json").data
    shift = api.post(url(ws, "pos/shifts/"), {"register_id": reg["id"]}, format="json").data
    tx = api.post(url(ws, "mpesa/transactions/prompt/"), {"phone": "0712345678", "amount": "1160"}, format="json").data
    line = [{"description": "Paint 4L", "quantity": "1", "unit_price": "1160", "tax_rate_id": vat16(ws)}]
    early = api.post(url(ws, "receipts/"), {"issue_date": day, "method": "mpesa", "shift_id": shift["id"], "lines": line,
                                            "prices_include_tax": True, "mpesa_transaction_id": tx["id"]}, format="json")
    assert early.status_code == 409  # not paid yet
    stk_callback(connected.callback_token)
    sale = api.post(url(ws, "receipts/"), {"issue_date": day, "method": "mpesa", "shift_id": shift["id"], "lines": line,
                                           "prices_include_tax": True, "mpesa_transaction_id": tx["id"]}, format="json")
    assert sale.status_code == 201 and sale.data["payment_reference"] == "SJK1ABC234"
    assert api.get(url(ws, f"mpesa/transactions/{tx['id']}/")).data["receipt_number"] == sale.data["number"]
