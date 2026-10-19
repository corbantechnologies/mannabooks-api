"""Money helpers. Amounts are Decimal with 2 places (numeric(18,2)); rates have 6 places."""
from decimal import ROUND_HALF_UP, Decimal

ZERO = Decimal("0.00")
CENT = Decimal("0.01")
MONEY_FIELD = {"max_digits": 18, "decimal_places": 2}
RATE_FIELD = {"max_digits": 18, "decimal_places": 6}


def q2(value) -> Decimal:
    """Round to cents, half up (how KRA and Kenyan banks round)."""
    return Decimal(str(value or 0)).quantize(CENT, rounding=ROUND_HALF_UP)
