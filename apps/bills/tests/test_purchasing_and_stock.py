from decimal import Decimal as D

import pytest

from apps.invoices.tests.test_sales_flow import customer, tb, url, vat16

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


def supplier(api, ws, **extra):
    return api.post(url(ws, "suppliers/"), {"name": "Bamburi Cement Ltd", "kra_pin": "P000222333R", "payment_terms_days": 30, **extra},
                    format="json").data


def stock_product(api, ws, name="Cement 50kg", cost="700", price="1000"):
    return api.post(url(ws, "products/"), {"name": name, "sale_price": price, "cost_price": cost, "tax_rate_id": vat16(ws),
                                           "track_inventory": True, "reorder_level": "5"}, format="json").data


def level(api, ws, product):
    rows = api.get(url(ws, "stock/levels/"), {"product": product["id"]}).data["results"]
    if not rows:
        return D(0), D(0)
    return sum((D(r["quantity"]) for r in rows), D(0)), D(rows[0]["average_cost"])


def test_order_receive_bill_and_pay(api, ws, day, add_member, client_for):
    sup = supplier(api, ws)
    assert sup["number"] == "SUP-0001"
    cement = stock_product(api, ws)
    po = api.post(url(ws, "purchase-orders/"), {"supplier_id": sup["id"], "order_date": day,
                                                "lines": [{"product_id": cement["id"], "quantity": "10", "unit_cost": "700"}]}, format="json")
    assert po.status_code == 201 and po.data["number"].startswith("PO-") and po.data["total"] == "8120.00"
    store = client_for(add_member(ws, "store@example.com", "store-manager"))
    assert store.post(url(ws, f"purchase-orders/{po.data['id']}/action/"), {"action": "approve"}, format="json").status_code == 403
    grn_early = api.post(url(ws, "goods-receipts/"), {"purchase_order_id": po.data["id"], "receipt_date": day,
                                                       "lines": [{"order_line_id": po.data["lines"][0]["id"], "quantity": "6"}]}, format="json")
    assert grn_early.status_code == 409  # not approved yet
    api.post(url(ws, f"purchase-orders/{po.data['id']}/action/"), {"action": "approve"}, format="json")
    grn = store.post(url(ws, "goods-receipts/"), {"purchase_order_id": po.data["id"], "receipt_date": day, "delivery_note_number": "DN-881",
                                                   "lines": [{"order_line_id": po.data["lines"][0]["id"], "quantity": "6"}]}, format="json")
    assert grn.status_code == 201, grn.data
    assert grn.data["total_value"] == "4200.00" and level(api, ws, cement) == (D("6"), D("700"))
    assert api.get(url(ws, f"purchase-orders/{po.data['id']}/")).data["status"] == "partially_received"
    rows = tb(ws, day)
    assert rows["1300"]["debit"] == D("4200.00") and rows["2050"]["credit"] == D("4200.00")
    too_many = store.post(url(ws, "goods-receipts/"), {"purchase_order_id": po.data["id"], "receipt_date": day,
                                                        "lines": [{"order_line_id": po.data["lines"][0]["id"], "quantity": "5"}]}, format="json")
    assert too_many.status_code == 409

    bill = api.post(url(ws, "bills/"), {"goods_receipt_id": grn.data["id"], "supplier_invoice_number": "BCL-5521", "bill_date": day}, format="json")
    assert bill.status_code == 201, bill.data
    assert bill.data["total"] == "4872.00" and len(bill.data["lines"]) == 1
    posted = api.post(url(ws, f"bills/{bill.data['id']}/post/"))
    assert posted.status_code == 200 and posted.data["status"] == "posted" and posted.data["number"].startswith("BILL-")
    rows = tb(ws, day)
    assert "2050" not in rows and rows["1400"]["debit"] == D("672.00") and rows["2000"]["credit"] == D("4872.00")
    from apps.ledgeraccounts.models import LedgerAccount

    rent = str(LedgerAccount.objects.get(workspace=ws, code="6010").id)
    dup = api.post(url(ws, "bills/"), {"supplier_id": sup["id"], "supplier_invoice_number": "bcl-5521", "bill_date": day,
                                       "lines": [{"description": "Rent", "quantity": "1", "unit_cost": "100", "account_id": rent}]}, format="json")
    assert dup.status_code == 201 and api.post(url(ws, f"bills/{dup.data['id']}/post/")).status_code == 409  # same supplier invoice twice
    api.delete(url(ws, f"bills/{dup.data['id']}/"))
    assert api.get(url(ws, f"suppliers/{sup['id']}/")).data["balance"] == "4872.00"

    bank = str(LedgerAccount.objects.get(workspace=ws, system_key="bank").id)
    pv = api.post(url(ws, "payment-vouchers/"), {"supplier_id": sup["id"], "lines": [{"bill_id": bill.data["id"], "amount": "4872"}]}, format="json")
    assert pv.status_code == 201 and pv.data["status"] == "draft" and pv.data["withholding_amount"] == "0.00"
    assert api.post(url(ws, f"payment-vouchers/{pv.data['id']}/action/"), {"action": "pay", "method": "bank", "paid_from_id": bank},
                    format="json").status_code == 409  # not approved
    api.post(url(ws, f"payment-vouchers/{pv.data['id']}/action/"), {"action": "approve"}, format="json")  # the Owner may approve their own
    paid = api.post(url(ws, f"payment-vouchers/{pv.data['id']}/action/"), {"action": "pay", "method": "bank", "paid_from_id": bank,
                                                                            "payment_date": day, "reference": "EFT-001"}, format="json")
    assert paid.data["status"] == "paid" and paid.data["payment_number"].startswith("SPAY-")
    assert api.get(url(ws, f"bills/{bill.data['id']}/")).data["status"] == "paid"
    assert api.get(url(ws, f"suppliers/{sup['id']}/")).data["balance"] == "0.00"
    statement = api.get(url(ws, f"suppliers/{sup['id']}/statement/")).data
    assert [r["kind"] for r in statement["rows"]] == ["bill", "payment"]


def test_service_order_bill_with_withholding_tax(api, ws, day):
    from apps.ledgeraccounts.models import LedgerAccount
    from apps.taxrates.models import TaxRate

    wht = TaxRate.objects.get(workspace=ws, code="WHT5")
    sup = supplier(api, ws, name="Ken Consulting", withholding_tax_rate_id=str(wht.id))
    fees = str(LedgerAccount.objects.get(workspace=ws, code="6080").id)
    so = api.post(url(ws, "service-orders/"), {"supplier_id": sup["id"], "scope": "Audit the books",
                                               "lines": [{"description": "Audit fee", "quantity": "1", "unit_cost": "50000", "account_id": fees,
                                                          "tax_rate_id": vat16(ws)}]}, format="json")
    assert so.status_code == 201 and so.data["total"] == "58000.00"
    api.post(url(ws, f"service-orders/{so.data['id']}/action/"), {"action": "approve"}, format="json")
    done = api.post(url(ws, "service-completions/"), {"service_order_id": so.data["id"], "completion_date": day, "rating": 5}, format="json")
    assert done.status_code == 201 and api.get(url(ws, f"service-orders/{so.data['id']}/")).data["status"] == "completed"
    bill = api.post(url(ws, "bills/"), {"service_order_id": so.data["id"], "supplier_invoice_number": "KC-77", "bill_date": day}, format="json")
    api.post(url(ws, f"bills/{bill.data['id']}/post/"))
    assert tb(ws, day)["6080"]["debit"] == D("50000.00")
    pv = api.post(url(ws, "payment-vouchers/"), {"supplier_id": sup["id"], "lines": [{"bill_id": bill.data["id"], "amount": "58000"}]}, format="json")
    assert pv.status_code == 201, pv.data
    assert pv.data["withholding_amount"] == "2500.00" and pv.data["net_payable"] == "55500.00"  # 5% of the 50,000 before VAT
    bank = str(LedgerAccount.objects.get(workspace=ws, system_key="bank").id)
    api.post(url(ws, f"payment-vouchers/{pv.data['id']}/action/"), {"action": "approve"}, format="json")
    api.post(url(ws, f"payment-vouchers/{pv.data['id']}/action/"), {"action": "pay", "method": "bank", "paid_from_id": bank, "payment_date": day},
             format="json")
    rows = tb(ws, day)
    assert rows["2110"]["credit"] == D("2500.00") and rows["1100"]["credit"] == D("55500.00")
    assert api.get(url(ws, f"bills/{bill.data['id']}/")).data["status"] == "paid"


def test_sales_take_stock_and_post_cost(api, ws, day):
    from apps.ledgeraccounts.models import LedgerAccount

    cement = stock_product(api, ws)
    wh = api.get(url(ws, "warehouses/")).data["results"][0]
    assert wh["name"] == "Main store"
    opening = api.post(url(ws, "stock-adjustments/"), {"warehouse_id": wh["id"], "adjustment_date": day, "reason": "opening",
                                                       "lines": [{"product_id": cement["id"], "quantity": "10", "unit_cost": "700"}]}, format="json")
    assert opening.status_code == 201 and opening.data["total_value"] == "7000.00"
    assert tb(ws, day)["3200"]["credit"] == D("7000.00")
    cust = customer(api, ws)
    too_many = api.post(url(ws, "invoices/"), {"customer_id": cust["id"], "issue_date": day, "lines": [{"product_id": cement["id"], "quantity": "11"}]},
                        format="json").data
    assert api.post(url(ws, f"invoices/{too_many['id']}/issue/")).status_code == 409
    inv = api.post(url(ws, "invoices/"), {"customer_id": cust["id"], "issue_date": day, "lines": [{"product_id": cement["id"], "quantity": "4"}]},
                   format="json").data
    api.post(url(ws, f"invoices/{inv['id']}/issue/"))
    assert level(api, ws, cement)[0] == D("6") and tb(ws, day)["5000"]["debit"] == D("2800.00")
    assert api.get(url(ws, "products/", ), {"search": "Cement"}).data["results"][0]["stock_on_hand"] == "6.000"
    cash = str(LedgerAccount.objects.get(workspace=ws, system_key="cash").id)
    sale = api.post(url(ws, "receipts/"), {"issue_date": day, "method": "cash", "deposit_account_id": cash, "prices_include_tax": True,
                                           "lines": [{"product_id": cement["id"], "quantity": "1"}]}, format="json")
    assert sale.status_code == 201 and level(api, ws, cement)[0] == D("5")
    api.post(url(ws, f"receipts/{sale.data['id']}/void/"), {"reason": "x"}, format="json")
    assert level(api, ws, cement)[0] == D("6")
    cn = api.post(url(ws, "credit-notes/"), {"invoice_id": inv["id"], "issue_date": day, "reason": "1 bag returned",
                                             "lines": [{"product_id": cement["id"], "quantity": "1"}]}, format="json")
    assert cn.status_code == 201 and level(api, ws, cement)[0] == D("7")
    assert tb(ws, day)["5000"]["debit"] == D("2100.00")
    low = api.get(url(ws, "stock/levels/"), {"low": "true"}).data["count"]
    assert low == 0
    card = api.get(url(ws, "stock/movements/"), {"product": cement["id"]}).data
    assert {m["kind"] for m in card["results"]} >= {"adjustment", "sale", "sale_return", "reversal"}


def test_transfer_adjust_count_and_produce(api, ws, day):
    cement = stock_product(api, ws)
    sand = stock_product(api, ws, name="Sand (bag)", cost="100", price="150")
    blocks = stock_product(api, ws, name="Concrete block", cost="0", price="80")
    main = api.get(url(ws, "warehouses/")).data["results"][0]
    shop = api.post(url(ws, "warehouses/"), {"name": "Thika shop"}, format="json").data
    api.post(url(ws, "stock-adjustments/"), {"warehouse_id": main["id"], "adjustment_date": day, "reason": "opening",
                                             "lines": [{"product_id": cement["id"], "quantity": "20", "unit_cost": "700"},
                                                       {"product_id": sand["id"], "quantity": "50", "unit_cost": "100"}]}, format="json")
    trf = api.post(url(ws, "stock-transfers/"), {"from_warehouse_id": main["id"], "to_warehouse_id": shop["id"], "transfer_date": day,
                                                 "lines": [{"product_id": cement["id"], "quantity": "5"}]}, format="json")
    assert trf.status_code == 201 and trf.data["total_value"] == "3500.00"
    by_place = {r["warehouse_name"]: D(r["quantity"]) for r in api.get(url(ws, "stock/levels/"), {"product": cement["id"]}).data["results"]}
    assert by_place == {"Main store": D("15"), "Thika shop": D("5")}
    damaged = api.post(url(ws, "stock-adjustments/"), {"warehouse_id": main["id"], "adjustment_date": day, "reason": "damaged",
                                                       "lines": [{"product_id": cement["id"], "quantity": "-1"}]}, format="json")
    assert damaged.data["total_value"] == "-700.00" and tb(ws, day)["5100"]["debit"] == D("700.00")
    take = api.post(url(ws, "stock-takes/"), {"warehouse_id": main["id"], "count_date": day}, format="json")
    assert take.status_code == 201 and len(take.data["lines"]) == 3
    api.post(url(ws, f"stock-takes/{take.data['id']}/counts/"), {"counts": [{"product_id": cement["id"], "counted_quantity": "13"},
                                                                         {"product_id": sand["id"], "counted_quantity": "50"}]}, format="json")
    posted = api.post(url(ws, f"stock-takes/{take.data['id']}/action/"), {"action": "post"}, format="json")
    assert posted.data["status"] == "posted" and posted.data["difference_value"] == "-700.00"
    assert level(api, ws, cement)[0] == D("18")  # 13 in Main store + 5 in the shop

    bom = api.post(url(ws, "bills-of-materials/"), {"product_id": blocks["id"], "output_quantity": "10",
                                                    "lines": [{"component_id": cement["id"], "quantity": "1"}, {"component_id": sand["id"], "quantity": "3"}]},
                   format="json")
    assert bom.status_code == 201, bom.data
    mo = api.post(url(ws, "production-orders/"), {"bom_id": bom.data["id"], "quantity": "20", "warehouse_id": main["id"], "production_date": day},
                  format="json")
    assert mo.status_code == 201 and [line["quantity"] for line in mo.data["lines"]] == ["2.000", "6.000"]
    done = api.post(url(ws, f"production-orders/{mo.data['id']}/action/"), {"action": "complete"}, format="json")
    assert done.data["status"] == "completed" and done.data["total_cost"] == "2000.00" and done.data["unit_cost"] == "100.0000"
    assert level(api, ws, blocks) == (D("20"), D("100"))
