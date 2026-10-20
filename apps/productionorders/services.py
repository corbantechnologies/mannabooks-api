from decimal import Decimal

from django.db import transaction

from apps.core.exceptions import BusinessRuleError
from apps.core.money import ZERO
from apps.sequences.services import next_value
from apps.stockmovements.services import COST, Source, move_in, move_out

from .models import ProductionOrder, ProductionOrderLine

S = ProductionOrder.Status


@transaction.atomic
def plan(workspace, *, bom, quantity, warehouse, production_date, notes="", user=None) -> ProductionOrder:
    if not bom.is_active:
        raise BusinessRuleError("This recipe is inactive.")
    if bom.product.made_to_order:
        raise BusinessRuleError(f"{bom.product} is made to order: its ingredients come out of stock when it is sold, so it isn't produced ahead.")
    if quantity <= 0:
        raise BusinessRuleError("The quantity must be more than zero.")
    order = ProductionOrder.objects.create(workspace=workspace, created_by=user, number=next_value(workspace, "production_order"), bom=bom,
                                           quantity=quantity, warehouse=warehouse, production_date=production_date, notes=notes)
    factor = Decimal(quantity) / bom.output_quantity
    ProductionOrderLine.objects.bulk_create(
        ProductionOrderLine(order=order, component=line.component, quantity=(line.quantity * factor).quantize(Decimal("0.001")))
        for line in bom.lines.select_related("component")
    )
    return order


def set_usage(order: ProductionOrder, usage: list[dict]) -> ProductionOrder:
    if order.status != S.PLANNED:
        raise BusinessRuleError("This order is finished.")
    lines = {line.component_id: line for line in order.lines.all()}
    for row in usage:
        line = lines.get(row["component"].pk)
        if line is None or row["quantity"] < 0:
            raise BusinessRuleError(f"{row['component']}: not on this order, or a negative quantity.")
        line.quantity = row["quantity"]
        line.save(update_fields=["quantity", "updated_at"])
    return order


@transaction.atomic
def complete(order: ProductionOrder) -> ProductionOrder:
    order = ProductionOrder.objects.select_for_update().get(pk=order.pk)
    if order.status != S.PLANNED:
        raise BusinessRuleError("This order is already finished.")
    source, total = Source("production_order", order.pk, order.number), ZERO
    for line in order.lines.select_related("component"):
        if line.quantity <= 0:
            continue
        mv = move_out(product=line.component, warehouse=order.warehouse, quantity=line.quantity, kind="production_out", source=source,
                      date=order.production_date)
        line.unit_cost, line.value = mv.unit_cost, -mv.value
        line.save(update_fields=["unit_cost", "value", "updated_at"])
        total += -mv.value
    order.total_cost, order.unit_cost = total, (total / order.quantity).quantize(COST)
    move_in(product=order.bom.product, warehouse=order.warehouse, quantity=order.quantity, unit_cost=order.unit_cost, kind="production_in",
            source=source, date=order.production_date)
    order.status = S.COMPLETED
    order.save(update_fields=["status", "total_cost", "unit_cost", "updated_at"])
    return order


def cancel(order: ProductionOrder) -> ProductionOrder:
    if order.status != S.PLANNED:
        raise BusinessRuleError("A completed order can't be cancelled.")
    order.status = S.CANCELLED
    order.save(update_fields=["status", "updated_at"])
    return order
