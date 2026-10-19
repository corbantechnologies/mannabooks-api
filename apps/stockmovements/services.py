"""
The stock ledger. Every module changes stock only through `move_in`, `move_out` and `reverse_source`,
which keep each product's level and weighted average cost per warehouse, and refuse to go below zero.
"""
from dataclasses import dataclass
from decimal import Decimal

from django.db import transaction

from apps.core.exceptions import BusinessRuleError
from apps.core.money import ZERO, q2

from .models import StockLevel, StockMovement

QTY = Decimal("0.001")
COST = Decimal("0.0001")


@dataclass
class Source:
    type: str
    id: object
    number: str = ""


def _level(product, warehouse) -> StockLevel:
    StockLevel.objects.get_or_create(workspace=warehouse.workspace, product=product, warehouse=warehouse)
    return StockLevel.objects.select_for_update().get(product=product, warehouse=warehouse)


def _check(product, warehouse):
    if not product.track_inventory:
        raise BusinessRuleError(f"{product} doesn't track stock. Switch on Track stock on the product.")
    if warehouse.workspace_id != product.workspace_id:
        raise BusinessRuleError("That warehouse belongs to another workspace.")


@transaction.atomic
def move_in(*, product, warehouse, quantity, unit_cost, kind, source: Source, date) -> StockMovement:
    _check(product, warehouse)
    quantity, unit_cost = Decimal(quantity).quantize(QTY), Decimal(unit_cost).quantize(COST)
    if quantity <= 0:
        raise BusinessRuleError("The quantity must be more than zero.")
    level = _level(product, warehouse)
    new_qty = level.quantity + quantity
    level.average_cost = ((level.quantity * level.average_cost + quantity * unit_cost) / new_qty).quantize(COST) if new_qty > 0 else unit_cost
    level.quantity = new_qty
    level.save(update_fields=["quantity", "average_cost", "updated_at"])
    return StockMovement.objects.create(
        workspace=warehouse.workspace, product=product, warehouse=warehouse, movement_date=date, kind=kind, quantity=quantity,
        unit_cost=unit_cost, value=q2(quantity * unit_cost), balance_quantity=new_qty, source_type=source.type,
        source_id=source.id, source_number=source.number,
    )


@transaction.atomic
def move_out(*, product, warehouse, quantity, kind, source: Source, date) -> StockMovement:
    """Take stock out at the current average cost."""
    _check(product, warehouse)
    quantity = Decimal(quantity).quantize(QTY)
    if quantity <= 0:
        raise BusinessRuleError("The quantity must be more than zero.")
    level = _level(product, warehouse)
    if level.quantity < quantity:
        raise BusinessRuleError(f"Only {level.quantity.normalize():f} {product.unit} of {product} in {warehouse}; {quantity.normalize():f} needed.")
    level.quantity -= quantity
    level.save(update_fields=["quantity", "updated_at"])
    return StockMovement.objects.create(
        workspace=warehouse.workspace, product=product, warehouse=warehouse, movement_date=date, kind=kind, quantity=-quantity,
        unit_cost=level.average_cost, value=-q2(quantity * level.average_cost), balance_quantity=level.quantity,
        source_type=source.type, source_id=source.id, source_number=source.number,
    )


@transaction.atomic
def reverse_source(source_type: str, source_id, date) -> Decimal:
    """Undo every movement of a document with opposite movements at the same cost. Returns the value put back."""
    total = ZERO
    movements = list(StockMovement.objects.filter(source_type=source_type, source_id=source_id).exclude(kind="reversal")
                     .select_related("product", "warehouse"))
    reversed_already = StockMovement.objects.filter(source_type=source_type, source_id=source_id, kind="reversal").exists()
    if reversed_already:
        return ZERO
    source = Source(source_type, source_id, movements[0].source_number if movements else "")
    for m in movements:
        if m.quantity < 0:
            mv = move_in(product=m.product, warehouse=m.warehouse, quantity=-m.quantity, unit_cost=m.unit_cost, kind="reversal", source=source, date=date)
        else:
            level = _level(m.product, m.warehouse)
            if level.quantity < m.quantity:
                raise BusinessRuleError(f"{m.product}: {m.quantity.normalize():f} were received but only {level.quantity.normalize():f} are left in {m.warehouse}. "
                                        "Record what happened to the rest first.")
            level.quantity -= m.quantity
            if level.quantity > 0 and level.quantity:
                remaining_value = (level.quantity + m.quantity) * level.average_cost - m.quantity * m.unit_cost
                level.average_cost = max((remaining_value / level.quantity).quantize(COST), ZERO)
            level.save(update_fields=["quantity", "average_cost", "updated_at"])
            mv = StockMovement.objects.create(
                workspace=m.workspace, product=m.product, warehouse=m.warehouse, movement_date=date, kind="reversal", quantity=-m.quantity,
                unit_cost=m.unit_cost, value=-m.value, balance_quantity=level.quantity, source_type=source_type, source_id=source_id,
                source_number=m.source_number,
            )
        total += -mv.value
    return total


def value_of(source_type: str, source_id) -> Decimal:
    from django.db.models import Sum

    return StockMovement.objects.filter(source_type=source_type, source_id=source_id).aggregate(s=Sum("value"))["s"] or ZERO
