from django.db import transaction

from apps.core.exceptions import BusinessRuleError
from apps.core.money import ZERO
from apps.products.models import Product
from apps.sequences.services import next_value
from apps.stockadjustments.services import adjust_line, post_value
from apps.stockmovements.models import StockLevel
from apps.stockmovements.services import Source

from .models import StockTake, StockTakeLine

S = StockTake.Status


@transaction.atomic
def start(workspace, *, warehouse, count_date, category=None, notes="", user=None) -> StockTake:
    if StockTake.objects.filter(warehouse=warehouse, status=S.COUNTING).exists():
        raise BusinessRuleError(f"A count of {warehouse} is already in progress. Post or cancel it first.")
    take = StockTake.objects.create(workspace=workspace, created_by=user, number=next_value(workspace, "stock_take"), warehouse=warehouse,
                                    category=category, count_date=count_date, notes=notes)
    products = Product.objects.filter(workspace=workspace, track_inventory=True, is_active=True)
    if category is not None:
        products = products.filter(category=category)
    levels = dict(StockLevel.objects.filter(warehouse=warehouse).values_list("product_id", "quantity"))
    StockTakeLine.objects.bulk_create(StockTakeLine(stock_take=take, product=p, system_quantity=levels.get(p.id, ZERO)) for p in products)
    if not take.lines.exists():
        raise BusinessRuleError("No products track stock here yet. Switch on Track stock on your products first.")
    return take


def record_counts(take: StockTake, counts: list[dict]) -> StockTake:
    if take.status != S.COUNTING:
        raise BusinessRuleError("This count is finished.")
    lines = {line.product_id: line for line in take.lines.all()}
    for row in counts:
        line = lines.get(row["product"].pk)
        if line is None:
            raise BusinessRuleError(f"{row['product']} isn't on this count.")
        if row["counted_quantity"] is not None and row["counted_quantity"] < 0:
            raise BusinessRuleError("Counts can't be negative.")
        line.counted_quantity = row["counted_quantity"]
        line.save(update_fields=["counted_quantity", "updated_at"])
    return take


@transaction.atomic
def post(take: StockTake, user=None) -> StockTake:
    """Move stock to the counted quantities. Sales since the count started are allowed for: the difference uses the
    count against the books at the start."""
    take = StockTake.objects.select_for_update().get(pk=take.pk)
    if take.status != S.COUNTING:
        raise BusinessRuleError("This count is finished.")
    counted = [line for line in take.lines.select_related("product") if line.counted_quantity is not None]
    if not counted:
        raise BusinessRuleError("Enter at least one count.")
    source, total = Source("stock_take", take.pk, take.number), ZERO
    for line in counted:
        line.difference = line.counted_quantity - line.system_quantity
        if line.difference:
            mv = adjust_line(product=line.product, warehouse=take.warehouse, quantity=line.difference, unit_cost=None, kind="stock_take",
                             source=source, date=take.count_date)
            line.unit_cost, line.value = mv.unit_cost, mv.value
            total += mv.value
        line.save(update_fields=["difference", "unit_cost", "value", "updated_at"])
    take.status, take.difference_value = S.POSTED, total
    take.save(update_fields=["status", "difference_value", "updated_at"])
    post_value(take.workspace, source="stock_take", source_model="stocktakes.StockTake", source_id=take.pk, date=take.count_date,
               number=take.number, value=total, label=f"Stock take {take.number}", user=user)
    return take


def cancel(take: StockTake) -> StockTake:
    if take.status != S.COUNTING:
        raise BusinessRuleError("Only a count in progress can be cancelled.")
    take.status = S.CANCELLED
    take.save(update_fields=["status", "updated_at"])
    return take
