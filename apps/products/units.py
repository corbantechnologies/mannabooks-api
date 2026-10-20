"""Which unit a document line is in, and how many of the product's own unit that is."""
from decimal import Decimal

from apps.core.exceptions import BusinessRuleError

ONE = Decimal("1")


def conversion(product, unit: str | None, line_no: int | None = None):
    """(unit, factor, ProductUnit or None). Blank or the product's own unit is a factor of 1."""
    unit = (unit or "").strip()
    if product is None or not unit or unit == product.unit:
        return (product.unit if product is not None and not unit else unit), ONE, None
    match = next((u for u in product.units.all() if u.unit == unit), None)
    if match is None:
        where = f"Line {line_no}: " if line_no else ""
        raise BusinessRuleError(f"{where}{product} isn't sold or bought in {unit}. Add it under Other units on the product.")
    return match.unit, match.factor, match
