from decimal import Decimal as D

import pytest

from apps.bills.tests.test_purchasing_and_stock import api, day, level, stock_product, ws  # noqa: F401
from apps.invoices.tests.test_sales_flow import tb, url

pytestmark = pytest.mark.django_db


def stock_in(api, ws, day, product, quantity, cost):  # noqa: F811 (fixtures passed in)
    wh = api.get(url(ws, "warehouses/")).data["results"][0]
    api.post(url(ws, "stock-adjustments/"), {"warehouse_id": wh["id"], "adjustment_date": day, "reason": "opening",
                                             "lines": [{"product_id": product["id"], "quantity": quantity, "unit_cost": cost}]}, format="json")


def test_recipe_cost_and_margin(api, ws, day):  # noqa: F811
    flour = stock_product(api, ws, name="Flour 1kg", cost="100", price="150")
    sugar = stock_product(api, ws, name="Sugar 1kg", cost="200", price="250")
    stock_in(api, ws, day, flour, "10", "120")  # the stock on hand cost more than the cost price says
    cake = stock_product(api, ws, name="Cake", cost="0", price="200")
    bom = api.post(url(ws, "bills-of-materials/"), {"product_id": cake["id"], "output_quantity": "4",
                                                    "lines": [{"component_id": flour["id"], "quantity": "2"},
                                                              {"component_id": sugar["id"], "quantity": "0.5"}]}, format="json")
    assert bom.status_code == 201, bom.data
    cost = bom.data["costing"]
    # 2 kg flour at 120 (stock average) + 0.5 kg sugar at 200 (no stock: cost price) = 340 a batch of 4
    assert cost["batch_cost"] == "340.00" and cost["unit_cost"] == "85.0000"
    assert cost["margin"] == "115.00" and cost["margin_percent"] == "57.50"
    assert [line["cost"] for line in bom.data["lines"]] == ["240.00", "100.00"]
    listed = api.get(url(ws, "bills-of-materials/")).data["results"][0]
    assert listed["costing"]["unit_cost"] == "85.0000"


def test_made_to_order_takes_ingredients_when_sold(api, ws, day):  # noqa: F811
    from apps.ledgeraccounts.models import LedgerAccount

    beef = stock_product(api, ws, name="Beef 1kg", cost="600", price="700")
    buns = stock_product(api, ws, name="Burger bun", cost="20", price="30")
    stock_in(api, ws, day, beef, "5", "600")
    stock_in(api, ws, day, buns, "50", "20")
    burger = api.post(url(ws, "products/"), {"name": "Burger", "sale_price": "500", "made_to_order": True, "track_inventory": True}, format="json")
    assert burger.status_code == 400 and "made_to_order" in burger.data["errors"]  # no stock of its own
    burger = api.post(url(ws, "products/"), {"name": "Burger", "sale_price": "500", "made_to_order": True}, format="json").data
    cash = str(LedgerAccount.objects.get(workspace=ws, system_key="cash").id)

    def sell(quantity):
        return api.post(url(ws, "receipts/"), {"issue_date": day, "method": "cash", "deposit_account_id": cash,
                                               "lines": [{"product_id": burger["id"], "quantity": quantity}]}, format="json")

    no_recipe = sell("1")
    assert no_recipe.status_code == 409 and "no active recipe" in no_recipe.data["message"]
    bom = api.post(url(ws, "bills-of-materials/"), {"product_id": burger["id"], "output_quantity": "1",
                                                    "lines": [{"component_id": beef["id"], "quantity": "0.2"},
                                                              {"component_id": buns["id"], "quantity": "1"}]}, format="json")
    assert bom.status_code == 201 and bom.data["made_to_order"] and bom.data["costing"]["unit_cost"] == "140.0000"
    sale = sell("3")
    assert sale.status_code == 201, sale.data
    assert level(api, ws, beef)[0] == D("4.4") and level(api, ws, buns)[0] == D("47")
    assert tb(ws, day)["5000"]["debit"] == D("420.00")  # 3 burgers at 140
    api.post(url(ws, f"receipts/{sale.data['id']}/void/"), {"reason": "x"}, format="json")
    assert level(api, ws, beef)[0] == D("5") and level(api, ws, buns)[0] == D("50")
    wh = api.get(url(ws, "warehouses/")).data["results"][0]
    ahead = api.post(url(ws, "production-orders/"), {"bom_id": bom.data["id"], "quantity": "2", "warehouse_id": wh["id"], "production_date": day},
                     format="json")
    assert ahead.status_code == 409
