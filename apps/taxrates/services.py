from decimal import Decimal

from apps.ledgeraccounts.models import LedgerAccount

from .models import TaxRate

# (code, name, kind, rate, eTIMS code, sales account key, purchases account key, default)
DEFAULT_TAX_RATES = [
    ("VAT16", "VAT 16%", "vat", "16", "B", "vat_output", "vat_input", True),
    ("VAT8", "VAT 8% (petroleum products)", "vat", "8", "E", "vat_output", "vat_input", False),
    ("ZERO", "Zero-rated (0%)", "vat", "0", "C", "vat_output", "vat_input", False),
    ("EXEMPT", "Exempt from VAT", "vat", "0", "A", "", "", False),
    ("NONVAT", "Not subject to VAT", "vat", "0", "D", "", "", False),
    ("WHVAT2", "Withholding VAT 2%", "withholding_vat", "2", "", "wht_vat_receivable", "vat_output", False),
    ("WHT5", "Withholding tax 5% (professional and management fees)", "withholding_tax", "5", "", "wht_receivable", "wht_payable", False),
]


def seed_tax_rates(workspace, user=None) -> None:
    accounts = {a.system_key: a for a in LedgerAccount.objects.filter(workspace=workspace).exclude(system_key="")}
    existing = set(TaxRate.objects.filter(workspace=workspace).values_list("code", flat=True))
    # The default rate for new lines: VAT 16% if the business is VAT registered, otherwise Not subject to VAT.
    default_code = "VAT16" if workspace.vat_registered else "NONVAT"
    TaxRate.objects.bulk_create(
        TaxRate(workspace=workspace, code=code, name=name, kind=kind, rate=Decimal(rate), etims_code=etims,
                sales_account=accounts.get(sales_key), purchases_account=accounts.get(purchases_key),
                is_default=code == default_code and not existing, created_by=user)
        for code, name, kind, rate, etims, sales_key, purchases_key, _default in DEFAULT_TAX_RATES
        if code not in existing
    )


def match_default_to_vat_status(workspace) -> None:
    """After VAT registration changes, swap the default between VAT 16% and Not subject to VAT.

    Only the seeded pair is swapped: a default the business chose itself is left alone.
    """
    want, other = ("VAT16", "NONVAT") if workspace.vat_registered else ("NONVAT", "VAT16")
    rates = TaxRate.objects.filter(workspace=workspace, code__in=[want, other])
    if not rates.filter(code=other, is_default=True).exists():
        return
    rates.filter(code=other).update(is_default=False)
    rates.filter(code=want).update(is_default=True, is_active=True)
