from decimal import Decimal as D

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from apps.invoices.tests.test_sales_flow import url

pytestmark = pytest.mark.django_db


def csv_file(text, name="list.csv"):
    return SimpleUploadedFile(name, text.encode("utf-8"), content_type="text/csv")


def test_import_check_then_commit_and_export(workspace, owner, client_for):
    from apps.customers.models import Customer
    from apps.products.models import Product

    api = client_for(owner)
    template = api.get(url(workspace, "imports/templates/customers/"))
    assert template.status_code == 200 and template.content.decode().startswith("name,kind,kra_pin")

    bad = "name,kind,kra_pin,email\nBaraka Supplies,company,P000111222Q,accounts@baraka.co.ke\nNo PIN Ltd,company,12345,x@y.co\n"
    checked = api.post(url(workspace, "imports/"), {"kind": "customers", "file": csv_file(bad), "commit": "true"}, format="multipart")
    assert checked.status_code == 201 and checked.data["status"] == "failed" and checked.data["errors"][0]["row"] == 3, checked.data
    assert Customer.objects.filter(workspace=workspace).count() == 0  # all or nothing

    good = "Name,Kind,KRA PIN,Email,Phone\nBaraka Supplies,company,P000111222Q,accounts@baraka.co.ke,0722000111\nJane Wanjiku,individual,,,0711000222\n"
    dry = api.post(url(workspace, "imports/"), {"kind": "customers", "file": csv_file(good)}, format="multipart").data
    assert dry["status"] == "checked" and dry["imported_rows"] == 2 and Customer.objects.filter(workspace=workspace).count() == 0
    done = api.post(url(workspace, "imports/"), {"kind": "customers", "file": csv_file(good), "commit": "true"}, format="multipart").data
    assert done["status"] == "imported" and Customer.objects.filter(workspace=workspace).count() == 2
    again = api.post(url(workspace, "imports/"), {"kind": "customers", "file": csv_file(good), "commit": "true"}, format="multipart").data
    assert again["skipped_rows"] == 2 and again["imported_rows"] == 0  # importing twice adds nothing

    products = ("name,code,kind,category,unit,sale_price,cost_price,vat,track_stock,quantity_on_hand\n"
                "Cement 50kg,CEM-50,goods,Building materials,bag,950,780,NONVAT,yes,120\nDelivery,,service,,trip,500,,NONVAT,no,\n")
    imported = api.post(url(workspace, "imports/"), {"kind": "products", "file": csv_file(products), "commit": "true"}, format="multipart").data
    assert imported["status"] == "imported", imported
    cement = Product.objects.get(workspace=workspace, code="CEM-50")
    assert cement.category.name == "Building materials" and cement.track_inventory
    levels = api.get(url(workspace, "stock/levels/"), {"product": str(cement.id)}).data["results"]
    assert D(levels[0]["quantity"]) == D("120")

    opening = "account_code,debit,credit\n1100,250000,\n3000,,250000\n"
    no_date = api.post(url(workspace, "imports/"), {"kind": "opening_balances", "file": csv_file(opening), "commit": "true"}, format="multipart")
    assert no_date.status_code == 409
    from apps.periods.models import AccountingPeriod

    day = AccountingPeriod.objects.filter(workspace=workspace).order_by("start_date").first().start_date.isoformat()
    ob = api.post(url(workspace, "imports/"), {"kind": "opening_balances", "file": csv_file(opening), "commit": "true", "as_of": day}, format="multipart").data
    assert ob["status"] == "imported" and ob["imported_rows"] == 2
    draft = api.get(url(workspace, "opening-balances/")).data
    assert draft["status"] == "draft" and len(draft["lines"]) == 2

    exported = api.get(url(workspace, "exports/customers/"))
    text = exported.content.decode("utf-8-sig")
    assert exported.status_code == 200 and "Baraka Supplies" in text and text.splitlines()[0].startswith("number,name")
    assert api.get(url(workspace, "exports/products/")).content.decode("utf-8-sig").count("\n") == 3
    assert api.get(url(workspace, "imports/")).data["count"] == 7
