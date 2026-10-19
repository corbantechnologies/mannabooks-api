from decimal import Decimal

from apps.core.exceptions import BusinessRuleError
from apps.currencies.models import Currency

from .models import ExchangeRate


def rate_on(workspace, code: str, on_date) -> Decimal:
    """The latest rate on or before `on_date`. The base currency is always 1."""
    currency = Currency.objects.filter(workspace=workspace, code=code.upper()).first()
    if currency is None:
        raise BusinessRuleError(f"{code} is not set up as a currency in this workspace.")
    if currency.is_base:
        return Decimal("1")
    rate = (
        ExchangeRate.objects.filter(workspace=workspace, currency=currency, rate_date__lte=on_date)
        .order_by("-rate_date")
        .values_list("rate", flat=True)
        .first()
    )
    if rate is None:
        raise BusinessRuleError(f"There is no {currency.code} exchange rate on or before {on_date}. Add one first.")
    return rate
