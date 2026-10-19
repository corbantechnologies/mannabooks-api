from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from apps.core.exceptions import BusinessRuleError
from apps.core.money import ZERO, q2

from .models import StatutoryRate

BANDS = [{"upto": 24000, "rate": 10}, {"upto": 32333, "rate": 25}, {"upto": 500000, "rate": 30}, {"upto": 800000, "rate": 32.5}, {"upto": None, "rate": 35}]
DEFAULTS = [
    {"effective_from": date(2025, 2, 1), "nssf_lower_limit": 8000, "nssf_upper_limit": 72000, "notes": "NSSF year 3 limits"},
    {"effective_from": date(2026, 2, 1), "nssf_lower_limit": 9000, "nssf_upper_limit": 108000, "notes": "NSSF year 4 limits: confirm with NSSF"},
]


def seed(workspace) -> None:
    if not StatutoryRate.objects.filter(workspace=workspace).exists():
        StatutoryRate.objects.bulk_create(StatutoryRate(workspace=workspace, paye_bands=BANDS, **d) for d in DEFAULTS)


def rates_on(workspace, on: date) -> StatutoryRate:
    seed(workspace)
    rate = StatutoryRate.objects.filter(workspace=workspace, effective_from__lte=on).first()
    if rate is None:
        raise BusinessRuleError(f"No payroll rates in force on {on:%d %b %Y}. Add them in Payroll > Statutory rates.")
    return rate


def paye_before_relief(bands, taxable: Decimal) -> Decimal:
    tax, lower = ZERO, ZERO
    for band in bands:
        upper = Decimal(str(band["upto"])) if band.get("upto") is not None else None
        if taxable <= lower:
            break
        portion = (min(taxable, upper) if upper is not None else taxable) - lower
        tax += portion * Decimal(str(band["rate"])) / 100
        if upper is None:
            break
        lower = upper
    return q2(tax)


def compute(rate: StatutoryRate, *, gross: Decimal, taxable_earnings: Decimal) -> dict:
    """Statutory deductions on a month's pay. `gross` is all earnings; `taxable_earnings` leaves out tax-free ones."""
    def pct(amount, rate_):
        return (amount * Decimal(rate_) / 100).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    nssf = pct(min(gross, rate.nssf_upper_limit), rate.nssf_rate)
    shif = max(pct(gross, rate.shif_rate), rate.shif_minimum) if gross > 0 else ZERO
    housing = pct(gross, rate.housing_levy_rate)
    taxable = taxable_earnings - nssf - ((shif + housing) if rate.deductions_before_paye else ZERO)
    taxable = max(taxable, ZERO)
    before = paye_before_relief(rate.paye_bands, taxable)
    paye = max(before - rate.personal_relief, ZERO)
    return {"nssf_employee": nssf, "nssf_employer": nssf, "shif": shif, "housing_levy_employee": housing, "housing_levy_employer": housing,
            "taxable_pay": q2(taxable), "paye_before_relief": before, "personal_relief": min(rate.personal_relief, before), "paye": paye}
