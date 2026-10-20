from decimal import Decimal as D

import pytest

from apps.bills.tests.test_purchasing_and_stock import api, day, level, supplier, ws  # noqa: F401
from apps.invoices.tests.test_sales_flow import customer, tb, url, vat16

pytestmark = pytest.mark.django_db


def soda(api, ws):  # noqa: F811 (fixtures passed in)
    return api.post(url(ws, "products/"), {"name": "Soda 500ml", "sale_price": "80", "cost_price": "50", "tax_rate_id": vat16(ws), "unit": "pcs",
                                           "track_inventory": True, "units": [{"unit": "ctn", "factor": "24", "sale_price": "1800"}]},
                    format="json")


def test_buy_in_cartons_sell_in_cartons_and_pieces(api, ws, day):  # noqa: F811
    bad = api.post(url(ws, "products/"), {"name": "Juice", "sale_price": "80", "unit": "pcs", "units": [{"unit": "pcs", "factor": "6"}]}, format="json")
    assert bad.status_code == 400 and "units" in bad.data["errors"]
    item = soda(api, ws)
    assert item.status_code == 201 and item.data["units"][0]["unit"] == "ctn", item.data
    item = item.data

    sup = supplier(api, ws)
    po = api.post(url(ws, "purchase-orders/"), {"supplier_id": sup["id"], "order_date": day,
                                                "lines": [{"product_id": item["id"], "quantity": "2", "unit": "ctn"}]}, format="json").data
    assert po["lines"][0]["unit_cost"] == "1200.0000" and po["lines"][0]["unit_factor"] == "24.0000"  # 24 x the cost of a piece
    api.post(url(ws, f"purchase-orders/{po['id']}/action/"), {"action": "approve"}, format="json")
    grn = api.post(url(ws, "goods-receipts/"), {"purchase_order_id": po["id"], "receipt_date": day,
                                                "lines": [{"order_line_id": po["lines"][0]["id"], "quantity": "2"}]}, format="json")
    assert grn.status_code == 201, grn.data
    assert level(api, ws, item) == (D("48"), D("50"))  # stock is kept in pieces

    cust = customer(api, ws)
    inv = api.post(url(ws, "invoices/"), {"customer_id": cust["id"], "issue_date": day,
                                          "lines": [{"product_id": item["id"], "quantity": "1", "unit": "ctn"}]}, format="json").data
    assert inv["lines"][0]["unit_price"] == "1800.0000" and inv["lines"][0]["unit"] == "ctn"
    assert api.post(url(ws, f"invoices/{inv['id']}/issue/")).status_code == 200
    assert level(api, ws, item)[0] == D("24") and tb(ws, day)["5000"]["debit"] == D("1200.00")

    from apps.ledgeraccounts.models import LedgerAccount

    cash = str(LedgerAccount.objects.get(workspace=ws, system_key="cash").id)
    sale = api.post(url(ws, "receipts/"), {"issue_date": day, "method": "cash", "deposit_account_id": cash,
                                           "lines": [{"product_id": item["id"], "quantity": "3"}]}, format="json")
    assert sale.status_code == 201 and sale.data["lines"][0]["unit"] == "pcs" and sale.data["lines"][0]["unit_price"] == "80.0000"
    assert level(api, ws, item)[0] == D("21")
    wrong = api.post(url(ws, "invoices/"), {"customer_id": cust["id"], "issue_date": day,
                                            "lines": [{"product_id": item["id"], "quantity": "1", "unit": "kg"}]}, format="json")
    assert wrong.status_code == 409 and "isn't sold or bought in kg" in wrong.data["message"]

    cn = api.post(url(ws, "credit-notes/"), {"invoice_id": inv["id"], "issue_date": day, "reason": "Carton returned",
                                             "lines": [{"product_id": item["id"], "quantity": "1", "unit": "ctn"}]}, format="json")
    assert cn.status_code == 201, cn.data
    assert level(api, ws, item)[0] == D("45")

    bill = api.post(url(ws, "bills/"), {"supplier_id": sup["id"], "supplier_invoice_number": "S-77", "bill_date": day,
                                        "lines": [{"product_id": item["id"], "quantity": "1", "unit": "ctn", "unit_cost": "1440"}]}, format="json")
    assert bill.status_code == 201, bill.data
    assert api.post(url(ws, f"bills/{bill.data['id']}/post/")).status_code == 200
    quantity, cost = level(api, ws, item)
    assert quantity == D("69") and cost == D("53.4783")  # 45 at 50 and 24 at 60


def test_category_defaults_and_report(api, ws, day):  # noqa: F811
    from apps.ledgeraccounts.models import LedgerAccount
    from apps.taxrates.models import TaxRate

    zero = str(TaxRate.objects.get(workspace=ws, code="ZERO").id)
    drinks = api.post(url(ws, "product-categories/"), {"name": "Drinks", "tax_rate_id": zero, "markup_percent": "40"}, format="json")
    assert drinks.status_code == 201, drinks.data
    juices = api.post(url(ws, "product-categories/"), {"name": "Juices", "parent_id": drinks.data["id"]}, format="json").data
    juice = api.post(url(ws, "products/"), {"name": "Mango juice", "category_id": juices["id"], "cost_price": "100", "track_inventory": True,
                                            "opening_quantity": "10"}, format="json")
    assert juice.status_code == 201, juice.data
    assert str(juice.data["tax_rate_id"]) == zero and juice.data["sale_price"] == "140.0000"  # from the parent: zero-rated, cost + 40%
    priced = api.post(url(ws, "products/"), {"name": "Orange juice", "category_id": juices["id"], "cost_price": "100", "sale_price": "150",
                                             "tax_rate_id": vat16(ws)}, format="json").data
    assert priced["sale_price"] == "150.0000" and str(priced["tax_rate_id"]) == vat16(ws)  # what was entered wins
    other = api.post(url(ws, "products/"), {"name": "Nails", "sale_price": "10"}, format="json").data

    cash = str(LedgerAccount.objects.get(workspace=ws, system_key="cash").id)
    api.post(url(ws, "receipts/"), {"issue_date": day, "method": "cash", "deposit_account_id": cash,
                                    "lines": [{"product_id": juice.data["id"], "quantity": "2"}, {"product_id": other["id"], "quantity": "6"}]},
             format="json")
    report = api.get(url(ws, "reports/by-category/"), {"from": day, "to": day})
    assert report.status_code == 200, report.data
    rows = {r["name"]: r for r in report.data["rows"]}
    assert rows["Juices"]["sales"] == "280.00" and rows["Juices"]["stock_value"] == "800.00" and rows["Juices"]["products"] == 2
    assert rows["No category"]["sales"] == "60.00" and report.data["total_sales"] == "340.00"


def test_new_default_units(api, ws):  # noqa: F811
    abbreviations = {u["abbreviation"] for u in api.get(url(ws, "units/"), {"page_size": 100}).data["results"]}
    assert {"shot", "ctn", "btl", "ml"} <= abbreviations
