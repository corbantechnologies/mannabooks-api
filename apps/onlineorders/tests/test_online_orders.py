from decimal import Decimal as D

import pytest
from rest_framework.test import APIClient

from apps.invoices.tests.test_sales_flow import url, vat16
from apps.mpesatransactions.tests.test_mpesa_and_pos import api, connected, day, stk_callback, ws  # noqa: F401

pytestmark = pytest.mark.django_db
public = APIClient()


def stocked(api, ws, name="Paint 4l", price="1000", qty="5", online=True):  # noqa: F811 (fixtures passed in)
    return api.post(url(ws, "products/"), {"name": name, "sale_price": price, "cost_price": "600", "tax_rate_id": vat16(ws), "track_inventory": True,
                                           "opening_quantity": qty, "online": online}, format="json").data


def open_shop(api, ws, **extra):  # noqa: F811
    assert api.patch(url(ws, ""), {"store_enabled": True, "store_delivery_fee": "300", "store_intro": "Paint and hardware", **extra},
                     format="json").status_code == 200


def test_order_pay_on_pickup_then_complete_as_cash_sale(api, ws, day):  # noqa: F811
    assert public.get(f"/api/v1/store/{ws.slug}/").status_code == 404  # closed until switched on
    paint = stocked(api, ws)
    hidden = stocked(api, ws, name="Trade-only primer", online=False)
    open_shop(api, ws)
    shop = public.get(f"/api/v1/store/{ws.slug}/").data
    assert [p["name"] for p in shop["products"]] == ["Paint 4l"] and shop["products"][0]["price"] == "1160.00"  # with VAT
    assert not shop["mpesa"] and shop["delivery_fee"] == "300.00"

    order = {"customer_name": "Achieng Otieno", "phone": "0712345678", "fulfilment": "pickup", "payment_method": "on_delivery",
             "lines": [{"product_id": paint["id"], "quantity": "2"}]}
    too_many = public.post(f"/api/v1/store/{ws.slug}/orders/", {**order, "lines": [{"product_id": paint["id"], "quantity": "9"}]}, format="json")
    assert too_many.status_code == 409 and "left" in too_many.data["message"]
    not_online = public.post(f"/api/v1/store/{ws.slug}/orders/", {**order, "lines": [{"product_id": hidden["id"], "quantity": "1"}]}, format="json")
    assert not_online.status_code == 409
    mpesa = public.post(f"/api/v1/store/{ws.slug}/orders/", {**order, "payment_method": "mpesa"}, format="json")
    assert mpesa.status_code == 409  # this shop has no M-Pesa connection
    no_address = public.post(f"/api/v1/store/{ws.slug}/orders/", {**order, "fulfilment": "delivery"}, format="json")
    assert no_address.status_code == 409

    placed = public.post(f"/api/v1/store/{ws.slug}/orders/", order, format="json")
    assert placed.status_code == 201, placed.data
    assert placed.data["number"].startswith("WEB-") and placed.data["total"] == "2320.00" and placed.data["status"] == "new"
    token = placed.data["token"]
    assert api.get(f"/api/v1/w/{ws.slug}/context/").data["online_orders_new"] == 1
    mine = api.get(url(ws, "online-orders/")).data["results"][0]
    act = url(ws, f"online-orders/{mine['id']}/action/")
    assert api.post(act, {"action": "confirm"}, format="json").data["status"] == "confirmed"
    assert api.post(act, {"action": "ready"}, format="json").data["status"] == "ready"
    assert api.post(act, {"action": "complete"}, format="json").status_code == 409  # how did they pay?
    done = api.post(act, {"action": "complete", "method": "cash"}, format="json")
    assert done.status_code == 200 and done.data["status"] == "completed" and done.data["receipt_number"], done.data
    sale = api.get(url(ws, f"receipts/{done.data['receipt_id']}/")).data
    assert sale["total"] == "2320.00" and sale["customer_name"] == "Achieng Otieno"
    levels = api.get(url(ws, "stock/levels/"), {"product": paint["id"]}).data["results"]
    assert D(levels[0]["quantity"]) == D("3")
    assert public.get(f"/api/v1/store/{ws.slug}/orders/{token}/").data["status"] == "completed"
    assert public.get(f"/api/v1/store/{ws.slug}/orders/not-a-real-token/").status_code == 404
    assert api.post(act, {"action": "cancel", "reason": "x"}, format="json").status_code == 409  # completed already


def test_delivery_paid_by_mpesa(api, ws, day, connected):  # noqa: F811
    paint = stocked(api, ws)
    open_shop(api, ws)
    assert public.get(f"/api/v1/store/{ws.slug}/").data["mpesa"]
    placed = public.post(f"/api/v1/store/{ws.slug}/orders/", {
        "customer_name": "Achieng Otieno", "phone": "0712345678", "fulfilment": "delivery", "address": "Kileleshwa, Othaya Rd",
        "payment_method": "mpesa", "lines": [{"product_id": paint["id"], "quantity": "1"}]}, format="json")
    assert placed.status_code == 201 and placed.data["total"] == "1460.00" and placed.data["payment_status"] == "pending", placed.data
    stk_callback(connected.callback_token, amount=1460)
    token = placed.data["token"]
    assert public.get(f"/api/v1/store/{ws.slug}/orders/{token}/").data["payment_status"] == "paid"
    order = api.get(url(ws, "online-orders/")).data["results"][0]
    act = url(ws, f"online-orders/{order['id']}/action/")
    assert api.post(act, {"action": "cancel", "reason": "Out of stock"}, format="json").status_code == 409  # refund first
    done = api.post(act, {"action": "complete"}, format="json")  # paid online: no method needed
    assert done.status_code == 200, done.data
    sale = api.get(url(ws, f"receipts/{done.data['receipt_id']}/")).data
    assert sale["method"] == "mpesa" and sale["payment_reference"] == "SJK1ABC234" and sale["total"] == "1460.00"
