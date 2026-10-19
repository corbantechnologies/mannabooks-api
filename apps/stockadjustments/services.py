"""Stock changes outside sales and purchases, and their posting. Stock takes use `post_value` too."""
from decimal import Decimal

from django.db import transaction

from apps.core.exceptions import BusinessRuleError
from apps.core.money import ZERO
from apps.journals.services import LineInput, replace_for_source
from apps.ledgeraccounts.services import system_account
from apps.sequences.services import next_value
from apps.stockmovements.models import StockLevel
from apps.stockmovements.services import Source, move_in, move_out, reverse_source

from .models import StockAdjustment, StockAdjustmentLine


def post_value(workspace, *, source: str, source_model: str, source_id, date, number, value, label, opening=False, user=None):
    """Post a stock value change against Inventory: gains/losses, or Opening balance equity for opening stock."""
    lines = []
    if value:
        inventory = system_account(workspace, "inventory")
        other = system_account(workspace, "opening_balance_equity" if opening else "stock_adjustments")
        amount = abs(value)
        lines = ([LineInput(account=inventory, debit=amount, description=label), LineInput(account=other, credit=amount, description=label)]
                 if value > 0 else
                 [LineInput(account=other, debit=amount, description=label), LineInput(account=inventory, credit=amount, description=label)])
    replace_for_source(workspace, source=source, source_model=source_model, source_id=str(source_id), entry_date=date, reference=number,
                       description=label, lines=lines, user=user)


def adjust_line(*, product, warehouse, quantity, unit_cost, kind, source, date):
    """Move one product by a signed quantity. Increases use `unit_cost`, or the average cost, or the product's cost price."""
    quantity = Decimal(quantity)
    if quantity > 0:
        if unit_cost is None:
            level = StockLevel.objects.filter(product=product, warehouse=warehouse).first()
            unit_cost = level.average_cost if level and level.average_cost else product.cost_price
        return move_in(product=product, warehouse=warehouse, quantity=quantity, unit_cost=unit_cost, kind=kind, source=source, date=date)
    return move_out(product=product, warehouse=warehouse, quantity=-quantity, kind=kind, source=source, date=date)


@transaction.atomic
def create(workspace, *, warehouse, adjustment_date, reason, rows, notes="", user=None) -> StockAdjustment:
    if not rows:
        raise BusinessRuleError("Add at least one product.")
    adj = StockAdjustment.objects.create(workspace=workspace, created_by=user, number=next_value(workspace, "stock_adjustment"),
                                         warehouse=warehouse, adjustment_date=adjustment_date, reason=reason, notes=notes)
    source, total = Source("stock_adjustment", adj.pk, adj.number), ZERO
    for row in rows:
        if not row.get("quantity"):
            raise BusinessRuleError(f"{row['product']}: enter a quantity to add (positive) or remove (negative).")
        if reason == "opening" and row["quantity"] < 0:
            raise BusinessRuleError("Opening stock can only add stock.")
        mv = adjust_line(product=row["product"], warehouse=warehouse, quantity=row["quantity"], unit_cost=row.get("unit_cost"),
                         kind="adjustment", source=source, date=adjustment_date)
        StockAdjustmentLine.objects.create(adjustment=adj, product=row["product"], quantity=mv.quantity, unit_cost=mv.unit_cost, value=mv.value)
        total += mv.value
    adj.total_value = total
    adj.save(update_fields=["total_value", "updated_at"])
    post_value(workspace, source="stock_adjustment", source_model="stockadjustments.StockAdjustment", source_id=adj.pk, date=adjustment_date,
               number=adj.number, value=total, label=f"{adj.get_reason_display()} {adj.number}", opening=reason == "opening", user=user)
    return adj


@transaction.atomic
def void(adj: StockAdjustment, user=None) -> StockAdjustment:
    if adj.status == StockAdjustment.Status.VOID:
        raise BusinessRuleError("This adjustment is already void.")
    reverse_source("stock_adjustment", adj.pk, adj.adjustment_date)
    post_value(adj.workspace, source="stock_adjustment", source_model="stockadjustments.StockAdjustment", source_id=adj.pk,
               date=adj.adjustment_date, number=adj.number, value=ZERO, label="", user=user)
    adj.status = StockAdjustment.Status.VOID
    adj.save(update_fields=["status", "updated_at"])
    return adj
