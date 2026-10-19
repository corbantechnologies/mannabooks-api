from decimal import Decimal as D

import pytest

from apps.invoices.tests.test_sales_flow import tb, url, vat16

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


def accounts(api, ws):
    rows = api.get(url(ws, "bank-accounts/")).data["results"]
    return {r["name"]: r for r in rows}


def code_id(ws, code):
    from apps.ledgeraccounts.models import LedgerAccount

    return str(LedgerAccount.objects.get(workspace=ws, code=code).id)


def test_accounts_expenses_income_and_transfers(api, ws, day):
    acc = accounts(api, ws)
    assert {"Cash on hand", "Bank account", "M-Pesa", "Petty cash"} <= set(acc)
    equity = api.post(url(ws, "bank-accounts/"), {"name": "Equity Bank USD", "kind": "bank", "bank_name": "Equity", "account_number": "0123"}, format="json")
    assert equity.status_code == 201 and equity.data["ledger_code"] == "1160"
    fuel = api.post(url(ws, "expenses/"), {"expense_date": day, "paid_from_id": acc["M-Pesa"]["id"], "payee": "Rubis Thika Road", "method": "mpesa",
                                           "lines": [{"description": "Fuel", "quantity": "1", "unit_cost": "5800", "account_id": code_id(ws, "6040"),
                                                      "tax_rate_id": vat16(ws)}]}, format="json")
    assert fuel.status_code == 201, fuel.data
    assert fuel.data["total"] == "5800.00" and fuel.data["tax_total"] == "800.00"  # VAT inside the price by default
    income = api.post(url(ws, "other-income/"), {"income_date": day, "received_into_id": acc["Bank account"]["id"], "payer": "KCB interest",
                                                 "lines": [{"amount": "1200"}]}, format="json")
    assert income.status_code == 201 and income.data["lines"][0]["account_name"] == "Other income"
    t = api.post(url(ws, "bank-transfers/"), {"transfer_date": day, "from_account_id": acc["Bank account"]["id"], "to_account_id": acc["M-Pesa"]["id"],
                                              "amount": "10000", "fee": "50"}, format="json")
    assert t.status_code == 201
    rows = tb(ws, day)
    assert rows["6040"]["debit"] == D("5000.00") and rows["1400"]["debit"] == D("800.00") and rows["4500"]["credit"] == D("1200.00")
    assert rows["1150"]["debit"] == D("4200.00")  # 10,000 in - 5,800 fuel
    assert rows["1100"]["credit"] == D("8850.00")  # 1,200 in - 10,050 out
    assert rows["6090"]["debit"] == D("50.00")
    api.post(url(ws, f"expenses/{fuel.data['id']}/void/"), {"reason": "duplicate"}, format="json")
    assert "6040" not in tb(ws, day)


def test_statement_matching_and_reconciliation(api, ws, day):
    bank = accounts(api, ws)["Bank account"]
    income = api.post(url(ws, "other-income/"), {"income_date": day, "received_into_id": bank["id"], "payer": "Rent from tenant",
                                                 "lines": [{"amount": "30000"}]}, format="json").data
    imp = api.post(url(ws, "statement-lines/import/"), {"bank_account_id": bank["id"], "rows": [
        {"line_date": day, "description": "RTGS TENANT RENT", "reference": "FT2601", "amount": "30000"},
        {"line_date": day, "description": "LEDGER FEE", "reference": "CHG01", "amount": "-350"},
    ]}, format="json")
    assert imp.status_code == 201 and len(imp.data) == 2
    again = api.post(url(ws, "statement-lines/import/"), {"bank_account_id": bank["id"], "rows": [
        {"line_date": day, "description": "RTGS TENANT RENT", "reference": "FT2601", "amount": "30000"}]}, format="json")
    assert again.data == []  # duplicates are skipped
    rent_line, fee_line = imp.data[0], imp.data[1]
    sugg = api.get(url(ws, f"statement-lines/{rent_line['id']}/suggestions/")).data
    assert len(sugg) == 1 and sugg[0]["amount"] == "30000.00"
    matched = api.post(url(ws, f"statement-lines/{rent_line['id']}/action/"), {"action": "match", "journal_line_id": sugg[0]["journal_line_id"]}, format="json")
    assert matched.data["status"] == "matched"
    recorded = api.post(url(ws, f"statement-lines/{fee_line['id']}/action/"), {"action": "record", "account_id": code_id(ws, "6090")}, format="json")
    assert recorded.status_code == 200, recorded.data
    assert recorded.data["status"] == "matched" and tb(ws, day)["6090"]["debit"] == D("350.00")

    rec = api.post(url(ws, "reconciliations/"), {"bank_account_id": bank["id"], "statement_date": day, "statement_balance": "29650"}, format="json")
    assert rec.status_code == 201 and rec.data["difference"] == "0.00"  # both matched lines were ticked automatically
    lines = api.get(url(ws, f"reconciliations/{rec.data['id']}/lines/")).data
    assert len(lines) == 2 and all(line["cleared"] for line in lines)
    api.post(url(ws, f"reconciliations/{rec.data['id']}/lines/"), {"journal_line_ids": [lines[0]["journal_line_id"]], "cleared": False}, format="json")
    assert api.post(url(ws, f"reconciliations/{rec.data['id']}/action/"), {"action": "complete"}, format="json").status_code == 409
    api.post(url(ws, f"reconciliations/{rec.data['id']}/lines/"), {"journal_line_ids": [lines[0]["journal_line_id"]], "cleared": True}, format="json")
    done = api.post(url(ws, f"reconciliations/{rec.data['id']}/action/"), {"action": "complete"}, format="json")
    assert done.data["status"] == "completed"
    # a reconciled transaction is protected
    assert api.post(url(ws, f"other-income/{income['id']}/void/"), {"reason": "x"}, format="json").status_code == 409
    assert accounts(api, ws)["Bank account"]["last_reconciled"] == day
    nxt = api.post(url(ws, "reconciliations/"), {"bank_account_id": bank["id"], "statement_date": day, "statement_balance": "0"}, format="json")
    assert nxt.status_code == 409  # not after the last one
    api.post(url(ws, f"reconciliations/{rec.data['id']}/action/"), {"action": "reopen"}, format="json")
    assert api.post(url(ws, f"other-income/{income['id']}/void/"), {"reason": "x"}, format="json").status_code == 200
    assert api.get(url(ws, "statement-lines/"), {"status": "unmatched"}).data["count"] == 1  # the voided income freed its line
