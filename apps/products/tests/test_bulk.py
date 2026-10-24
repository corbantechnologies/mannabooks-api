import pytest

from apps.invoices.tests.test_sales_flow import api, url, vat16, ws  # noqa: F401

pytestmark = pytest.mark.django_db


def test_bulk_create_all_or_nothing(api, ws):  # noqa: F811
    cat = api.post(url(ws, "product-categories/"), {"name": "Laptops"}, format="json").data
    rows = [
        {"name": "ThinkPad X1", "sale_price": "100000", "category_id": cat["id"], "tax_rate_id": vat16(ws)},
        {"name": "Setup and imaging", "kind": "service", "sale_price": "2500", "code": "SVC-1"},
        {"name": "Mouse", "sale_price": "800", "cost_price": "500", "track_inventory": True, "opening_quantity": "12"},
    ]
    bad = api.post(url(ws, "products/bulk/"), {"products": [*rows, {"name": "", "sale_price": "-1"}, {"name": "Bag", "code": "svc-1"}]}, format="json")
    assert bad.status_code == 400 and set(bad.data["errors"]["rows"]) == {"3", "4"}, bad.data
    assert api.get(url(ws, "products/")).data["count"] == 0  # nothing saved

    res = api.post(url(ws, "products/bulk/"), {"products": rows}, format="json")
    assert res.status_code == 201, res.data
    assert [p["name"] for p in res.data] == ["ThinkPad X1", "Setup and imaging", "Mouse"]
    assert res.data[0]["code"] and res.data[0]["code"] != res.data[2]["code"]  # numbered one after another
    mouse = api.get(url(ws, f"products/{res.data[2]['id']}/")).data
    assert float(mouse["stock_on_hand"]) == 12
    assert api.post(url(ws, "products/bulk/"), {"products": [{"name": "x"}] * 51}, format="json").status_code == 400
