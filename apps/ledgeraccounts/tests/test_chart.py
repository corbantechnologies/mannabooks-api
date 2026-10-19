import pytest

from apps.ledgeraccounts.models import LedgerAccount

pytestmark = pytest.mark.django_db


def test_chart_rules(workspace, owner, client_for):
    api = client_for(owner)
    url = f"/api/v1/w/{workspace.slug}/ledger-accounts/"
    receivable = LedgerAccount.objects.get(workspace=workspace, system_key="receivable")
    assert api.delete(f"{url}{receivable.id}/").status_code == 409
    assert api.patch(f"{url}{receivable.id}/", {"is_active": False}, format="json").status_code == 400
    assert api.patch(f"{url}{receivable.id}/", {"name": "Debtors"}, format="json").status_code == 200

    bad = api.post(url, {"code": "6300", "name": "Cleaning", "account_type": "expense", "subtype": "bank"}, format="json")
    assert bad.status_code == 400 and "subtype" in bad.data["errors"]
    dup = api.post(url, {"code": "6010", "name": "Cleaning", "account_type": "expense", "subtype": "expense"}, format="json")
    assert dup.status_code == 400 and "code" in dup.data["errors"]
    ok = api.post(url, {"code": "6300", "name": "Cleaning", "account_type": "expense", "subtype": "expense"}, format="json")
    assert ok.status_code == 201
    assert api.delete(f"{url}{ok.data['id']}/").status_code == 204


def test_currencies_rates_and_tax_rates(workspace, owner, client_for):
    from apps.currencies.models import Currency
    from apps.exchangerates.services import rate_on

    api = client_for(owner)
    usd = Currency.objects.get(workspace=workspace, code="USD")
    kes = Currency.objects.get(workspace=workspace, code="KES")
    rates = f"/api/v1/w/{workspace.slug}/exchange-rates/"
    assert api.post(rates, {"currency_id": str(kes.id), "rate_date": "2026-01-02", "rate": "1"}, format="json").status_code == 400
    assert api.post(rates, {"currency_id": str(usd.id), "rate_date": "2026-01-02", "rate": "129.5"}, format="json").status_code == 201
    from datetime import date

    assert str(rate_on(workspace, "USD", date(2026, 3, 1))) == "129.500000"
    assert rate_on(workspace, "KES", date(2026, 3, 1)) == 1
    base = api.patch(f"/api/v1/w/{workspace.slug}/currencies/{kes.id}/", {"is_active": False}, format="json")
    assert base.status_code == 400

    taxes = api.get(f"/api/v1/w/{workspace.slug}/tax-rates/").data["results"]
    assert {t["code"] for t in taxes} >= {"VAT16", "ZERO", "EXEMPT", "WHVAT2"}


def test_chart_is_listed_in_code_order_with_balances(workspace, owner, client_for):
    from apps.journals import services
    from apps.periods.models import AccountingPeriod

    day = AccountingPeriod.objects.filter(workspace=workspace).order_by("start_date").first().start_date
    services.post_lines(workspace, entry_date=day, description="Capital", source="manual", lines=[
        services.LineInput(account=LedgerAccount.objects.get(workspace=workspace, code="1100"), debit=500),
        services.LineInput(account=LedgerAccount.objects.get(workspace=workspace, code="3000"), credit=500)])
    rows = client_for(owner).get(f"/api/v1/w/{workspace.slug}/ledger-accounts/").data
    codes = [r["code"] for r in rows]
    assert codes == sorted(codes)
    balances = {r["code"]: r["balance"] for r in rows}
    assert balances["1100"] == "500.00" and balances["3000"] == "500.00"  # each on its normal side


def test_tax_rates_without_an_account_show_none(workspace, owner, client_for):
    rows = client_for(owner).get(f"/api/v1/w/{workspace.slug}/tax-rates/").data["results"]
    exempt = next(r for r in rows if r["code"] == "EXEMPT")
    assert exempt["sales_account_name"] is None
    assert next(r for r in rows if r["code"] == "VAT16")["sales_account_name"] == "2100 VAT payable (output VAT)"
