from decimal import Decimal as D

import pytest

from apps.importjobs.tests.test_imports import csv_file
from apps.invoices.tests.test_sales_flow import url

pytestmark = pytest.mark.django_db


def upload(api, workspace, kind, text):
    res = api.post(url(workspace, "imports/"), {"kind": kind, "file": csv_file(text), "commit": "true"}, format="multipart")
    assert res.status_code == 201, res.data
    return res.data


def test_staff_leads_accounts_and_assets(workspace, owner, client_for):
    from apps.employees.models import Employee
    from apps.fixedassets.models import FixedAsset
    from apps.leads.models import Lead
    from apps.ledgeraccounts.models import LedgerAccount

    api = client_for(owner)
    assert api.get(url(workspace, "imports/templates/employees/")).content.decode().startswith("first_name,last_name")

    staff = ("first_name,last_name,email,national_id,kra_pin,department,basic_salary,pay_method,mpesa_phone,nssf_number,shif_number\n"
             "Jane,Wanjiku,jane@example.co.ke,23456789,A001234567B,Finance,65000,M-Pesa,0711000222,NS1,SH1\n"
             "Otieno,Ouma,,34567890,,Finance,40000,bank,,NS2,SH2\n")
    done = upload(api, workspace, "employees", staff)
    assert done["status"] == "imported" and done["imported_rows"] == 2, done
    jane = Employee.objects.get(workspace=workspace, national_id="23456789")
    assert jane.basic_salary == D("65000") and jane.pay_method == "mpesa" and jane.on_payroll and jane.department.name == "Finance"
    assert upload(api, workspace, "employees", staff)["skipped_rows"] == 2  # importing twice adds nothing

    done = upload(api, workspace, "leads", "name,company,phone,source,estimated_value\nPeter Otieno,Otieno Hardware,0722111333,Expo,120000\n")
    assert done["imported_rows"] == 1 and Lead.objects.get(workspace=workspace, phone="0722111333").source == "event"

    chart = "code,name,type,subtype,parent_code\n6151,Mobile data,expense,,6150\n6150,Internet and phone,expense,expense,\n"  # child before parent
    done = upload(api, workspace, "accounts", chart)
    assert done["imported_rows"] == 2, done
    assert LedgerAccount.objects.get(workspace=workspace, code="6151").parent.code == "6150"

    assets = ("name,category,serial_number,purchase_date,cost,residual_value,method,rate_percent,depreciation_to_date,depreciated_to\n"
              "Toyota Probox,motor_vehicles,NCP-1,2023-03-15,1450000,200000,reducing_balance,25,540000,2025-12-31\n")
    done = upload(api, workspace, "fixed_assets", assets)
    assert done["imported_rows"] == 1, done
    van = FixedAsset.objects.get(workspace=workspace, serial_number="NCP-1")
    assert van.acquisition == "existing" and van.accumulated_depreciation == D("540000") and van.book_value == D("910000")

    bad = upload(api, workspace, "employees", "first_name,last_name,branch\nAmina,Hassan,Nowhere\n")
    assert bad["status"] == "failed" and "branch" in bad["errors"][0]["message"]


def test_prices_units_recipes_counts_and_open_documents(workspace, owner, client_for):
    from apps.bills.models import Bill
    from apps.billsofmaterials.models import BillOfMaterials
    from apps.invoices.models import Invoice
    from apps.journals.models import JournalLine
    from apps.pricelists.models import PriceListItem
    from apps.products.models import Product, ProductUnit
    from apps.stocktakes.models import StockTakeLine

    api = client_for(owner)
    upload(api, workspace, "products", "name,code,kind,unit,sale_price,cost_price,vat,track_stock,quantity_on_hand\n"
                                       "Burger bun,BUN,goods,pcs,30,20,NONVAT,yes,100\nChicken burger,BURGER,goods,pcs,650,0,NONVAT,yes,0\n"
                                       "Soda 500ml,SODA,goods,btl,60,40,NONVAT,yes,48\n")

    done = upload(api, workspace, "product_prices", "code,name,sale_price,price_list,list_price\nSODA,,65,Wholesale,55\nBUN,,30,,\n")
    assert done["imported_rows"] == 1 and done["skipped_rows"] == 1, done  # the bun's price didn't change
    soda = Product.objects.get(workspace=workspace, code="SODA")
    assert soda.sale_price == D("65") and PriceListItem.objects.get(product=soda).price == D("55")

    assert upload(api, workspace, "product_units", "product_code,unit,factor,sale_price\nSODA,crate,24,1400\n")["imported_rows"] == 1
    assert ProductUnit.objects.get(product=soda, unit="crate").factor == D("24")

    done = upload(api, workspace, "recipes", "product_code,output_quantity,component_code,quantity\nBURGER,1,BUN,1\n")
    assert done["imported_rows"] == 1 and BillOfMaterials.objects.get(product__code="BURGER").lines.count() == 1, done

    done = upload(api, workspace, "stock_counts", "product_code,counted_quantity\nSODA,20\nSODA,26\nBUN,97\n")  # a scanner lists each scan
    assert done["imported_rows"] == 2, done
    assert StockTakeLine.objects.get(product=soda).counted_quantity == D("46")

    upload(api, workspace, "customers", "name,kind\nBaraka Supplies Ltd,company\n")
    upload(api, workspace, "suppliers", "name,kind\nBamburi Cement Ltd,company\n")
    invoices = "customer,invoice_number,invoice_date,due_date,amount_due\nBaraka Supplies Ltd,OLD-0457,2026-01-28,2026-02-28,48500\n"
    done = upload(api, workspace, "open_invoices", invoices)
    assert done["imported_rows"] == 1, done
    old = Invoice.objects.get(workspace=workspace, number="OLD-0457")
    assert old.status == "issued" and old.balance_due == D("48500") and old.tax_total == 0
    lines = JournalLine.objects.filter(entry__source="invoice", entry__source_id=str(old.pk))
    assert {(line.account.system_key, line.debit, line.credit) for line in lines} == {
        ("receivable", D("48500"), D("0")), ("opening_balance_equity", D("0"), D("48500"))}  # not a new sale, no VAT
    assert upload(api, workspace, "open_invoices", invoices)["skipped_rows"] == 1

    done = upload(api, workspace, "open_bills", "supplier,supplier_invoice_number,bill_date,amount_due\nBamburi Cement Ltd,BC-77812,2026-01-02,126000\n")
    assert done["imported_rows"] == 1, done
    bill = Bill.objects.get(workspace=workspace, supplier_invoice_number="BC-77812")
    assert bill.status == "posted" and bill.balance_due == D("126000")
