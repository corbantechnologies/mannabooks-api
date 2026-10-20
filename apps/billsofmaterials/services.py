"""What a recipe costs to make, and taking a made-to-order product's ingredients out of stock when it is sold."""
from decimal import Decimal

from apps.core.money import ZERO, q2

from .models import BillOfMaterials

COST = Decimal("0.0001")
QTY = Decimal("0.001")


def current_cost(product) -> Decimal:
    """What one unit costs now: the average cost of the stock on hand across warehouses, else the product's cost price."""
    from apps.stockmovements.models import StockLevel

    levels = StockLevel.objects.filter(product=product, quantity__gt=0).values("quantity", "average_cost")
    quantity = sum((lv["quantity"] for lv in levels), ZERO)
    if quantity > 0:
        return (sum((lv["quantity"] * lv["average_cost"] for lv in levels), ZERO) / quantity).quantize(COST)
    return product.cost_price or ZERO


def costing(bom: BillOfMaterials) -> dict:
    """Each ingredient's cost for one batch, the cost of one finished unit, and the margin at the product's sale price."""
    lines = []
    for line in bom.lines.all():
        unit_cost = current_cost(line.component)
        lines.append({"line_id": line.pk, "unit_cost": unit_cost, "cost": q2(line.quantity * unit_cost)})
    batch = sum((row["cost"] for row in lines), ZERO)
    unit = (batch / bom.output_quantity).quantize(COST) if bom.output_quantity else ZERO
    price = bom.product.sale_price or ZERO
    margin = q2(price - unit) if price else None
    return {
        "lines": lines,
        "batch_cost": batch,
        "unit_cost": unit,
        "sale_price": price,
        "margin": margin,
        "margin_percent": q2(margin / price * 100) if price else None,
    }


def recipe_for(product) -> BillOfMaterials | None:
    return BillOfMaterials.objects.filter(product=product, is_active=True).prefetch_related("lines__component").order_by("created_at").first()


def ingredients_for(product, quantity) -> list[tuple]:
    """(ingredient, quantity) needed to make `quantity` of a made-to-order product. Raises if it has no active recipe."""
    from apps.core.exceptions import BusinessRuleError

    bom = recipe_for(product)
    if bom is None:
        raise BusinessRuleError(f"{product} is made to order but has no active recipe. Add one in Manufacturing > Recipes.")
    factor = Decimal(quantity) / bom.output_quantity
    return [(line.component, (line.quantity * factor).quantize(QTY)) for line in bom.lines.all()]

