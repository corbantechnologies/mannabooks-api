from datetime import date, timedelta

import pytest

from apps.invoices.tests.test_sales_flow import customer, draft_invoice, url, vat16

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


def cash_sale(api, ws, day, cust, amount="11600", redeem=0):
    return api.post(url(ws, "receipts/"), {
        "issue_date": day, "customer_id": cust["id"], "method": "cash", "prices_include_tax": True, "redeem_points": redeem,
        "lines": [{"description": "Paint", "quantity": "1", "unit_price": amount, "tax_rate_id": vat16(ws)}],
    }, format="json")


def test_earn_redeem_tiers_and_void(api, ws, day):
    cust = customer(api, ws, phone="0712345678")
    assert api.post(url(ws, "loyalty/members/"), {"customer_id": cust["id"]}, format="json").status_code == 409  # programme off
    api.put(url(ws, "loyalty/program/"), {"is_active": True, "spend_per_point": "100", "point_value": "1", "min_redeem_points": "50",
                                          "max_redeem_percent": 50, "expiry_months": 12}, format="json")
    api.post(url(ws, "loyalty/tiers/"), {"name": "Gold", "min_points": 150, "multiplier": "2"}, format="json")
    member = api.post(url(ws, "loyalty/members/"), {"customer_id": cust["id"]}, format="json")
    assert member.status_code == 201 and member.data["card_number"].startswith("LC-")
    first = cash_sale(api, ws, day, cust)  # 11,600 incl. VAT = 10,000 net -> 100 points
    assert first.status_code == 201
    m = api.get(url(ws, "loyalty/members/"), {"lookup": "+254 712 345 678"}).data["results"][0]
    assert m["points_balance"] == 100 and m["tier_name"] is None
    cash_sale(api, ws, day, cust, amount="5800")  # 5,000 net -> 50 points -> 150: Gold
    m = api.get(url(ws, f"loyalty/members/{m['id']}/")).data
    assert m["points_balance"] == 150 and m["tier_name"] == "Gold"
    assert cash_sale(api, ws, day, cust, amount="100", redeem=60).status_code == 409  # more than 50% of the sale
    redeem = cash_sale(api, ws, day, cust, amount="1160", redeem=100)  # 100 KES off; earns on 1,060 incl. VAT
    assert redeem.status_code == 201, redeem.data
    assert redeem.data["total"] == "1060.00" and redeem.data["lines"][0]["discount_amount"] == "100.00"
    m = api.get(url(ws, f"loyalty/members/{m['id']}/")).data
    assert m["points_balance"] == 150 - 100 + 18  # 913.79 net x Gold 2 = 18
    api.post(url(ws, f"receipts/{redeem.data['id']}/void/"), {"reason": "mistake"}, format="json")
    m = api.get(url(ws, f"loyalty/members/{m['id']}/")).data
    assert m["points_balance"] == 150
    kinds = [t["kind"] for t in api.get(url(ws, "loyalty/transactions/"), {"member": m["id"]}).data["results"]]
    assert sorted(kinds) == ["earn", "earn", "earn", "redeem", "reverse", "reverse"]


def test_points_expire(api, ws, day):
    from apps.loyaltytransactions.services import expire_due

    cust = customer(api, ws)
    api.put(url(ws, "loyalty/program/"), {"is_active": True, "expiry_months": 1}, format="json")
    member = api.post(url(ws, "loyalty/members/"), {"customer_id": cust["id"]}, format="json").data
    cash_sale(api, ws, day, cust)
    assert expire_due(date.today()) == 0
    assert expire_due(date.today() + timedelta(days=40)) == 1
    assert expire_due(date.today() + timedelta(days=40)) == 0
    assert api.get(url(ws, f"loyalty/members/{member['id']}/")).data["points_balance"] == 0
    adjusted = api.post(url(ws, f"loyalty/members/{member['id']}/adjust/"), {"points": 25, "reason": "Welcome bonus"}, format="json")
    assert adjusted.data["points_balance"] == 25


def test_portal_link_shows_invoice_and_pays(api, ws, day, monkeypatch):
    from rest_framework.test import APIClient

    from apps.mpesaconnections import daraja

    cust = customer(api, ws)
    inv = draft_invoice(api, ws, cust, day).data
    inv = api.post(url(ws, f"invoices/{inv['id']}/issue/")).data
    link = api.post(url(ws, "portal-links/"), {"customer_id": cust["id"], "invoice_id": inv["id"], "days": 7}, format="json")
    assert link.status_code == 201 and "/p/" in link.data["url"]
    token = link.data["url"].rsplit("/", 1)[1]
    public = APIClient()
    page = public.get(f"/api/v1/portal/{token}/")
    assert page.status_code == 200 and page.data["invoices"][0]["number"] == inv["number"] and page.data["mpesa_available"] is False
    assert page.data["business"]["name"] == "Acme Traders" and len(page.data["invoices"][0]["lines"]) == 1
    assert public.post(f"/api/v1/portal/{token}/pay/", {"invoice_id": inv["id"], "phone": "0712345678", "amount": "1160"}, format="json").status_code == 409
    api.put(url(ws, "mpesa/connection/"), {"shortcode": "174379", "consumer_key": "a", "consumer_secret": "b", "passkey": "c", "is_active": True}, format="json")
    monkeypatch.setattr(daraja, "stk_push", lambda conn, **kw: {"CheckoutRequestID": "ws_CO_9"})
    paid = public.post(f"/api/v1/portal/{token}/pay/", {"invoice_id": inv["id"], "phone": "0712345678", "amount": "1160"}, format="json")
    assert paid.status_code == 201 and paid.data["status"] == "pending"
    assert public.get(f"/api/v1/portal/{token}/pay/{paid.data['id']}/").data["status"] == "pending"
    api.delete(url(ws, f"portal-links/{link.data['id']}/"))
    assert public.get(f"/api/v1/portal/{token}/").status_code == 409
    assert public.get("/api/v1/portal/not-a-token/").status_code == 409
