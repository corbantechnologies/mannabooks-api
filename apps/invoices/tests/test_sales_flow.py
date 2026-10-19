from decimal import Decimal as D

import pytest

from apps.core.sales import price
from apps.ledgeraccounts.models import LedgerAccount
from apps.periods.models import AccountingPeriod
from apps.reports.services import trial_balance
from apps.taxrates.models import TaxRate

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
    return AccountingPeriod.objects.filter(workspace=ws).order_by("start_date").first().start_date.isoformat()


def url(ws, path):
    return f"/api/v1/w/{ws.slug}/{path}"


def vat16(ws):
    return str(TaxRate.objects.get(workspace=ws, code="VAT16").id)


def customer(api, ws, **extra):
    return api.post(url(ws, "customers/"), {"name": "Baraka Supplies Ltd", "kra_pin": "P000111222Q", "payment_terms_days": 30, **extra}, format="json").data


def draft_invoice(api, ws, cust, day, price="1000", qty="1"):
    return api.post(url(ws, "invoices/"), {
        "customer_id": cust["id"], "issue_date": day,
        "lines": [{"description": "Cement 50kg", "quantity": qty, "unit_price": price, "tax_rate_id": vat16(ws)}],
    }, format="json")


def tb(ws, day):
    return {r["code"]: r for r in trial_balance(ws, day)["rows"]}


def test_pricing_with_and_without_vat_in_the_price(ws):
    rate = TaxRate.objects.get(workspace=ws, code="VAT16")
    assert price(D("2"), D("500"), D("10"), rate, False) == (D("900.00"), D("144.00"), D("1044.00"))
    assert price(D("1"), D("900"), D("0"), rate, True) == (D("775.86"), D("124.14"), D("900.00"))
    exempt = TaxRate.objects.get(workspace=ws, code="EXEMPT")
    assert price(D("3"), D("100"), D("0"), exempt, False) == (D("300.00"), D("0.00"), D("300.00"))


def test_invoice_issue_posts_receivable_sales_and_vat(api, ws, day):
    cust = customer(api, ws)
    assert cust["number"] == "CUS-0001"
    draft = draft_invoice(api, ws, cust, day)
    assert draft.status_code == 201 and draft.data["status"] == "draft" and draft.data["total"] == "1160.00"
    assert draft.data["due_date"] > day  # 30-day terms
    issued = api.post(url(ws, f"invoices/{draft.data['id']}/issue/"))
    assert issued.status_code == 200 and issued.data["number"].startswith("INV-") and issued.data["status"] == "issued"
    assert issued.data["etims_status"] == "disabled"  # platform switch is off until KRA approval
    rows = tb(ws, day)
    assert rows["1200"]["debit"] == D("1160.00") and rows["4000"]["credit"] == D("1000.00") and rows["2100"]["credit"] == D("160.00")
    assert api.patch(url(ws, f"invoices/{draft.data['id']}/"), {"notes": "x"}, format="json").status_code == 409


def test_payments_drive_status_balance_and_statement(api, ws, day):
    cust = customer(api, ws)
    inv = draft_invoice(api, ws, cust, day).data
    api.post(url(ws, f"invoices/{inv['id']}/issue/"))
    bank = str(LedgerAccount.objects.get(workspace=ws, system_key="mpesa").id)

    no_code = api.post(url(ws, "payments/"), {"customer_id": cust["id"], "payment_date": day, "amount": "500", "method": "mpesa",
                                              "deposit_account_id": bank, "allocations": [{"invoice_id": inv["id"], "amount": "500"}]}, format="json")
    assert no_code.status_code == 409  # M-Pesa needs its transaction code
    part = api.post(url(ws, "payments/"), {"customer_id": cust["id"], "payment_date": day, "amount": "500", "method": "mpesa",
                                           "reference": "sjk3l2m9xx", "deposit_account_id": bank,
                                           "allocations": [{"invoice_id": inv["id"], "amount": "500"}]}, format="json")
    assert part.status_code == 201 and part.data["reference"] == "SJK3L2M9XX" and part.data["unallocated_amount"] == "0.00"
    invoice = api.get(url(ws, f"invoices/{inv['id']}/")).data
    assert invoice["status"] == "partially_paid" and invoice["balance_due"] == "660.00" and len(invoice["payments"]) == 1

    too_much = api.post(url(ws, "payments/"), {"customer_id": cust["id"], "payment_date": day, "amount": "700", "method": "cash",
                                               "deposit_account_id": bank, "allocations": [{"invoice_id": inv["id"], "amount": "700"}]}, format="json")
    assert too_much.status_code == 409
    rest = api.post(url(ws, "payments/"), {"customer_id": cust["id"], "payment_date": day, "amount": "700", "method": "bank",
                                           "deposit_account_id": bank, "allocations": [{"invoice_id": inv["id"], "amount": "660"}]}, format="json")
    assert rest.data["unallocated_amount"] == "40.00"
    assert api.get(url(ws, f"invoices/{inv['id']}/")).data["status"] == "paid"
    assert api.get(url(ws, f"customers/{cust['id']}/")).data["balance"] == "-40.00"  # in credit

    statement = api.get(url(ws, f"customers/{cust['id']}/statement/")).data
    assert [r["kind"] for r in statement["rows"]] == ["invoice", "payment", "payment"] and statement["closing_balance"] == "-40.00"

    assert api.post(url(ws, f"invoices/{inv['id']}/void/"), {"reason": "mistake"}, format="json").status_code == 409
    api.post(url(ws, f"payments/{rest.data['id']}/void/"), {"reason": "bounced"}, format="json")
    assert api.get(url(ws, f"invoices/{inv['id']}/")).data["status"] == "partially_paid"
    assert tb(ws, day)["1200"]["debit"] == D("660.00")


def test_credit_note_for_a_whole_invoice(api, ws, day):
    cust = customer(api, ws)
    inv = draft_invoice(api, ws, cust, day, qty="2").data
    api.post(url(ws, f"invoices/{inv['id']}/issue/"))
    cn = api.post(url(ws, "credit-notes/"), {"invoice_id": inv["id"], "issue_date": day, "reason": "Goods returned"}, format="json")
    assert cn.status_code == 201 and cn.data["total"] == "2320.00" and cn.data["applied_amount"] == "2320.00"
    assert api.get(url(ws, f"invoices/{inv['id']}/")).data["status"] == "paid"
    rows = tb(ws, day)
    assert "1200" not in rows and "2100" not in rows and rows.get("4000") is None
    api.post(url(ws, f"credit-notes/{cn.data['id']}/void/"), {"reason": "raised in error"}, format="json")
    assert api.get(url(ws, f"invoices/{inv['id']}/")).data["status"] == "issued"


def test_cash_sale_posts_to_cash_and_can_be_voided(api, ws, day):
    cash = str(LedgerAccount.objects.get(workspace=ws, system_key="cash").id)
    sale = api.post(url(ws, "receipts/"), {"issue_date": day, "customer_name": "Walk-in", "method": "cash", "deposit_account_id": cash,
                                           "lines": [{"description": "Nails 1kg", "quantity": "3", "unit_price": "232", "tax_rate_id": vat16(ws)}],
                                           "prices_include_tax": True}, format="json")
    assert sale.status_code == 201 and sale.data["number"].startswith("RCT-") and sale.data["total"] == "696.00"
    rows = tb(ws, day)
    assert rows["1000"]["debit"] == D("696.00") and rows["2100"]["credit"] == D("96.00") and rows["4000"]["credit"] == D("600.00")
    api.post(url(ws, f"receipts/{sale.data['id']}/void/"), {"reason": "keyed twice"}, format="json")
    assert "1000" not in tb(ws, day)


def test_quotation_converts_to_a_draft_invoice(api, ws, day):
    cust = customer(api, ws)
    product = api.post(url(ws, "products/"), {"name": "Site survey", "kind": "service", "sale_price": "15000", "tax_rate_id": vat16(ws)}, format="json").data
    quote = api.post(url(ws, "quotations/"), {"customer_id": cust["id"], "lines": [{"product_id": product["id"], "quantity": "1"}]}, format="json")
    assert quote.status_code == 201 and quote.data["number"].startswith("QT-") and quote.data["total"] == "17400.00"
    assert quote.data["lines"][0]["account_name"] == "Service income"
    api.post(url(ws, f"quotations/{quote.data['id']}/status/"), {"action": "accept"}, format="json")
    converted = api.post(url(ws, f"quotations/{quote.data['id']}/convert/"))
    invoice = api.get(url(ws, f"invoices/{converted.data['invoice_id']}/")).data
    assert invoice["status"] == "draft" and invoice["total"] == "17400.00"
    assert api.get(url(ws, f"quotations/{quote.data['id']}/")).data["status"] == "converted"
    assert api.delete(url(ws, f"products/{product['id']}/")).status_code == 409  # used on documents


def test_role_permissions_on_sales(api, ws, day, add_member, client_for):
    cust = customer(api, ws)
    inv = draft_invoice(api, ws, cust, day).data
    cashier = client_for(add_member(ws, "cashier@example.com", "cashier"))
    sales = client_for(add_member(ws, "sales@example.com", "sales"))
    assert cashier.post(url(ws, f"invoices/{inv['id']}/issue/")).status_code == 403
    assert sales.post(url(ws, f"invoices/{inv['id']}/issue/")).status_code == 200
    assert sales.post(url(ws, f"invoices/{inv['id']}/void/"), {"reason": "x"}, format="json").status_code == 403


def test_etims_signing_when_switched_on(api, ws, day, settings, monkeypatch, django_capture_on_commit_callbacks):
    from apps.etimssubmissions import client, tasks
    from apps.etimssubmissions.models import EtimsSubmission

    settings.ETIMS_ENABLED = True
    cust = customer(api, ws)
    inv = draft_invoice(api, ws, cust, day).data
    not_set_up = api.post(url(ws, f"invoices/{inv['id']}/issue/")).data
    assert not_set_up["etims_status"] == "not_configured"

    device = api.put(url(ws, "etims/device/"), {"kra_pin": "P051234567X", "branch_code": "00", "device_serial": "MB-0001",
                                                "communication_key": "secret-cmc-key", "is_active": True}, format="json")
    assert device.status_code == 200 and device.data["has_communication_key"] and "communication_key" not in device.data
    inv2 = draft_invoice(api, ws, cust, day).data
    with django_capture_on_commit_callbacks(execute=False) as callbacks:
        pending = api.post(url(ws, f"invoices/{inv2['id']}/issue/")).data
    assert pending["etims_status"] == "pending" and len(callbacks) == 1
    sub = EtimsSubmission.objects.get(document_id=inv2["id"])
    assert sub.kra_invoice_number == 1 and sub.payload["custTin"] == "P000111222Q"
    assert sub.payload["taxblAmtB"] == 1160.0 and sub.payload["taxAmtB"] == 160.0

    sent = {}
    monkeypatch.setattr(client, "save_sale", lambda device, payload: sent.setdefault("payload", payload) and
                        {"resultCd": "000", "data": {"sdcId": "KRACU0100000001", "rcptNo": 1, "rcptSign": "ABCD", "qrUrl": "https://etims.kra.go.ke/q"}})
    tasks.send_submission.apply(args=[str(sub.pk)])
    signed = api.get(url(ws, f"invoices/{inv2['id']}/")).data
    assert signed["etims_status"] == "signed" and signed["etims_cu_invoice_number"] == "KRACU0100000001/1"
    assert api.post(url(ws, f"invoices/{inv2['id']}/void/"), {"reason": "x"}, format="json").status_code == 409


def test_etims_connect_needs_the_platform_switch(api, ws, settings, monkeypatch):
    from apps.etimssubmissions import client

    api.put(url(ws, "etims/device/"), {"kra_pin": "P051234567X", "branch_code": "00", "device_serial": "OSCU-0001"}, format="json")
    off = api.post(url(ws, "etims/device/connect/"))
    assert off.status_code == 409 and "until KRA approval" in off.data["message"]

    settings.ETIMS_ENABLED = True
    monkeypatch.setattr(client, "initialise", lambda device: {"cmcKey": "KEY-FROM-KRA", "sdcId": "KRACU0100000001", "mrcNo": "WIS01"})
    on = api.post(url(ws, "etims/device/connect/"))
    assert on.status_code == 200 and on.data["has_communication_key"] and on.data["is_active"] and on.data["sdc_id"] == "KRACU0100000001"


def test_price_lists_categories_and_units(api, ws, day):
    units = api.get(url(ws, "units/")).data["results"]
    assert {"pcs", "kg"} <= {u["abbreviation"] for u in units}
    cat = api.post(url(ws, "product-categories/"), {"name": "Cement"}, format="json").data
    product = api.post(url(ws, "products/"), {"name": "Cement 50kg", "sale_price": "1000", "tax_rate_id": vat16(ws),
                                              "category_id": cat["id"], "unit": "bag"}, format="json").data
    other = api.post(url(ws, "products/"), {"name": "Sand (tonne)", "sale_price": "2000", "tax_rate_id": vat16(ws)}, format="json").data
    assert product["category_name"] == "Cement"
    wholesale = api.post(url(ws, "price-lists/"), {"name": "Wholesale", "adjust_percent": "-10",
                                                   "items": [{"product_id": product["id"], "price": "850"}]}, format="json")
    assert wholesale.status_code == 201
    cust = customer(api, ws, price_list_id=wholesale.data["id"])
    prices = {p["product_id"]: p["price"] for p in api.get(url(ws, "price-lists/customer-prices/"), {"customer": cust["id"]}).data}
    assert prices[product["id"]] == "850.0000" and prices[other["id"]] == "1800.00"
    inv = api.post(url(ws, "invoices/"), {"customer_id": cust["id"], "issue_date": day,
                                          "lines": [{"product_id": product["id"], "quantity": "2"},
                                                    {"product_id": other["id"], "quantity": "1", "discount_amount": "100"}]}, format="json")
    assert inv.status_code == 201
    assert [line["unit_price"] for line in inv.data["lines"]] == ["850.0000", "1800.0000"]
    assert inv.data["subtotal"] == "3400.00"  # 1700 + (1800 - 100)
    assert api.delete(url(ws, f"price-lists/{wholesale.data['id']}/")).status_code == 409


def test_debit_note_adds_to_an_invoice(api, ws, day):
    cust = customer(api, ws)
    inv = draft_invoice(api, ws, cust, day).data
    inv = api.post(url(ws, f"invoices/{inv['id']}/issue/")).data
    no_original = api.post(url(ws, "invoices/"), {"customer_id": cust["id"], "issue_date": day, "kind": "debit_note",
                                                  "lines": [{"description": "Transport", "quantity": "1", "unit_price": "500"}]}, format="json")
    assert no_original.status_code == 409
    dn = api.post(url(ws, "invoices/"), {"customer_id": cust["id"], "issue_date": day, "kind": "debit_note", "original_invoice_id": inv["id"],
                                         "lines": [{"description": "Transport", "quantity": "1", "unit_price": "500", "tax_rate_id": vat16(ws)}]}, format="json")
    issued = api.post(url(ws, f"invoices/{dn.data['id']}/issue/")).data
    assert issued["number"].startswith("DBN-") and issued["kind"] == "debit_note" and issued["original_invoice_number"] == inv["number"]
    assert api.get(url(ws, f"customers/{cust['id']}/")).data["balance"] == "1740.00"
    assert [r["kind"] for r in api.get(url(ws, f"customers/{cust['id']}/statement/")).data["rows"]] == ["invoice", "debit_note"]
    assert api.get(url(ws, "invoices/"), {"kind": "debit_note"}).data["count"] == 1


def test_delivery_note_from_an_invoice(api, ws, day):
    cust = customer(api, ws, address="Plot 12, Thika Road")
    inv = draft_invoice(api, ws, cust, day, qty="5").data
    dn = api.post(url(ws, "delivery-notes/"), {"invoice_id": inv["id"], "vehicle": "KDA 123A"}, format="json")
    assert dn.status_code == 201 and dn.data["number"].startswith("DN-") and dn.data["lines"][0]["quantity"] == "5.000"
    assert dn.data["delivery_address"] == "Plot 12, Thika Road" and dn.data["customer_name"] == cust["name"]
    done = api.post(url(ws, f"delivery-notes/{dn.data['id']}/status/"), {"action": "deliver", "received_by": "J. Otieno"}, format="json")
    assert done.data["status"] == "delivered" and done.data["received_by"] == "J. Otieno"
    assert api.patch(url(ws, f"delivery-notes/{dn.data['id']}/"), {"driver": "x"}, format="json").status_code == 409


def test_recurring_invoice_schedule():
    from datetime import date

    from apps.recurringinvoices.services import add_months

    assert add_months(date(2026, 1, 31), 1, 31) == date(2026, 2, 28)
    assert add_months(date(2026, 2, 28), 1, 31) == date(2026, 3, 31)
    assert add_months(date(2026, 11, 15), 3, 15) == date(2027, 2, 15)


def test_recurring_invoices_raise_and_issue(api, ws, day):
    from datetime import date, timedelta

    from apps.recurringinvoices.models import RecurringInvoice
    from apps.recurringinvoices.services import run_due

    cust = customer(api, ws)
    start = date.fromisoformat(day)
    rec = api.post(url(ws, "recurring-invoices/"), {
        "name": "Shop rent", "customer_id": cust["id"], "frequency": "monthly", "start_date": day, "auto_issue": True,
        "lines": [{"description": "Rent", "quantity": "1", "unit_price": "20000", "tax_rate_id": vat16(ws)}],
    }, format="json")
    assert rec.status_code == 201, rec.data
    assert rec.data["invoices_created"] == 1 and rec.data["last_invoice_number"].startswith("INV-")
    template = RecurringInvoice.objects.get(pk=rec.data["id"])
    assert template.next_run_date > start
    assert run_due(today=template.next_run_date - timedelta(days=1)) == 0
    assert run_due(today=template.next_run_date) == 1
    paused = api.post(url(ws, f"recurring-invoices/{rec.data['id']}/action/"), {"action": "pause"}, format="json")
    assert paused.data["status"] == "paused"


def test_payment_reminders(api, ws, day, mailoutbox):
    from datetime import date, timedelta

    from apps.reminders.services import run_due

    cust = customer(api, ws, email="accounts@baraka.co.ke")
    inv = draft_invoice(api, ws, cust, day).data
    api.post(url(ws, f"invoices/{inv['id']}/issue/"))
    rules = api.get(url(ws, "reminders/rules/")).data["results"]
    assert len(rules) == 4 and not any(r["is_active"] for r in rules)
    on_due = next(r for r in rules if r["days"] == 0)
    api.patch(url(ws, f"reminders/rules/{on_due['id']}/"), {"is_active": True}, format="json")
    due = api.get(url(ws, f"invoices/{inv['id']}/")).data["due_date"]
    assert run_due(today=date.fromisoformat(due) - timedelta(days=1)) == 0
    assert run_due(today=date.fromisoformat(due)) == 1
    assert run_due(today=date.fromisoformat(due)) == 0  # once per rule
    assert "Payment reminder" in mailoutbox[0].subject and "1,160.00" in mailoutbox[0].body
    manual = api.post(url(ws, "reminders/send/"), {"invoice_id": inv["id"]}, format="json")
    assert manual.status_code == 201 and len(mailoutbox) == 2
    assert api.get(url(ws, "reminders/sent/")).data["count"] == 2
