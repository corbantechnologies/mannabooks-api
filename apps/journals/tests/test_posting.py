from datetime import date
from decimal import Decimal as D

import pytest

from apps.core.exceptions import BusinessRuleError
from apps.journals import services
from apps.journals.models import JournalEntry
from apps.ledgeraccounts.models import LedgerAccount
from apps.periods.models import AccountingPeriod

pytestmark = pytest.mark.django_db


def acc(ws, code):
    return LedgerAccount.objects.get(workspace=ws, code=code)


def today_in(ws):
    return AccountingPeriod.objects.filter(workspace=ws).order_by("start_date").first().start_date


def test_workspace_starts_with_chart_taxes_currencies_and_year(workspace):
    assert LedgerAccount.objects.filter(workspace=workspace).count() >= 40
    assert acc(workspace, "1200").system_key == "receivable"
    from apps.currencies.models import Currency
    from apps.fiscalyears.models import FiscalYear
    from apps.taxrates.models import TaxRate

    assert Currency.objects.get(workspace=workspace, is_base=True).code == "KES"
    vat = TaxRate.objects.get(workspace=workspace, code="VAT16")
    assert vat.rate == D("16") and vat.etims_code == "B" and vat.sales_account.system_key == "vat_output"
    year = FiscalYear.objects.get(workspace=workspace)
    assert year.periods.count() == 12 and year.start_date.month == workspace.fiscal_year_start_month


def test_post_lines_checks_balance_and_numbers_entries(workspace, owner):
    day = today_in(workspace)
    bank, capital = acc(workspace, "1100"), acc(workspace, "3000")
    with pytest.raises(BusinessRuleError, match="must be equal"):
        services.post_lines(workspace, entry_date=day, description="x", source="manual", lines=[
            services.LineInput(account=bank, debit=100), services.LineInput(account=capital, credit=90)])
    with pytest.raises(BusinessRuleError, match="either a debit or a credit"):
        services.post_lines(workspace, entry_date=day, description="x", source="manual", lines=[
            services.LineInput(account=bank, debit=100, credit=100), services.LineInput(account=capital, credit=100)])
    entry = services.post_lines(workspace, entry_date=day, description="Capital", source="manual", user=owner, lines=[
        services.LineInput(account=bank, debit="1000.005"), services.LineInput(account=capital, credit="1000.005")])
    assert entry.status == "posted" and entry.number == f"JE-{date.today().year}-0001"
    assert entry.lines.get(account=bank).debit == D("1000.01")


def test_closed_and_missing_periods_block_posting(workspace):
    period = AccountingPeriod.objects.filter(workspace=workspace).order_by("start_date").first()
    period.status = "closed"
    period.save()
    lines = [services.LineInput(account=acc(workspace, "1100"), debit=5), services.LineInput(account=acc(workspace, "3000"), credit=5)]
    with pytest.raises(BusinessRuleError, match="is closed"):
        services.post_lines(workspace, entry_date=period.start_date, description="x", source="manual", lines=lines)
    with pytest.raises(BusinessRuleError, match="before your first financial year"):
        services.post_lines(workspace, entry_date=date(1990, 1, 1), description="x", source="manual", lines=lines)


def test_replace_for_source_deletes_in_open_periods_and_reverses_in_closed_ones(workspace):
    day = today_in(workspace)
    ar, sales = acc(workspace, "1200"), acc(workspace, "4000")
    src = {"source": "invoice", "source_model": "invoices.Invoice", "source_id": "inv-1"}

    def lines(amount):
        return [services.LineInput(account=ar, debit=amount), services.LineInput(account=sales, credit=amount)]

    first = services.replace_for_source(workspace, **src, entry_date=day, description="Invoice", lines=lines(100))
    second = services.replace_for_source(workspace, **src, entry_date=day, description="Invoice", lines=lines(150))
    assert not JournalEntry.objects.filter(pk=first.pk).exists()  # open period: replaced cleanly

    AccountingPeriod.objects.filter(workspace=workspace, start_date__lte=day, end_date__gte=day).update(status="closed")
    next_period = AccountingPeriod.objects.filter(workspace=workspace, start_date__gt=day).order_by("start_date").first()
    from unittest import mock

    with mock.patch("apps.journals.services.timezone.localdate", return_value=next_period.start_date):
        services.replace_for_source(workspace, **src, entry_date=next_period.start_date, description="Invoice", lines=lines(120))
    second.refresh_from_db()
    assert second.status == "reversed" and second.reversed_by.entry_date == next_period.start_date
    from apps.reports.services import trial_balance

    tb = trial_balance(workspace, next_period.end_date)
    row = next(r for r in tb["rows"] if r["code"] == "1200")
    assert row["debit"] == D("120.00") and tb["balanced"]


def test_manual_journal_api_flow(workspace, owner, add_member, client_for):
    api = client_for(owner)
    base = f"/api/v1/w/{workspace.slug}/journals/"
    day = today_in(workspace).isoformat()
    bank, rent = acc(workspace, "1100"), acc(workspace, "6010")
    body = {"entry_date": day, "description": "Rent for the month", "lines": [
        {"account_id": str(rent.id), "debit": "25000.00", "credit": "0"},
        {"account_id": str(bank.id), "debit": "0", "credit": "25000.00"},
    ]}
    draft = api.post(base, body, format="json")
    assert draft.status_code == 201 and draft.data["status"] == "draft" and draft.data["number"] == ""

    sales_user = client_for(add_member(workspace, "sales@example.com", "sales"))
    assert sales_user.post(f"{base}{draft.data['id']}/post/").status_code == 403

    posted = api.post(f"{base}{draft.data['id']}/post/")
    assert posted.status_code == 200 and posted.data["status"] == "posted" and posted.data["number"].startswith("JE-")
    assert api.patch(f"{base}{draft.data['id']}/", {"description": "x"}, format="json").status_code == 409
    assert api.delete(f"{base}{draft.data['id']}/").status_code == 409

    reversal = api.post(f"{base}{draft.data['id']}/reverse/", {"entry_date": day, "reason": "wrong month"}, format="json")
    assert reversal.status_code == 201 and reversal.data["reversal_of_number"] == posted.data["number"]
    ledger = api.get(f"/api/v1/w/{workspace.slug}/ledger-accounts/{rent.id}/ledger/").data
    assert [row["balance"] for row in ledger["lines"]] == ["25000.00", "0.00"]
    unbalanced = api.post(base, {**body, "lines": [body["lines"][0], {**body["lines"][1], "credit": "1"}]}, format="json")
    assert unbalanced.status_code == 201  # drafts may be unbalanced while being written...
    assert api.post(f"{base}{unbalanced.data['id']}/post/").status_code == 409  # ...but never posted
