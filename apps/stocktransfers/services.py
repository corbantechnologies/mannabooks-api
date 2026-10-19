from decimal import Decimal

from django.db import transaction

from apps.core.exceptions import BusinessRuleError
from apps.core.money import ZERO
from apps.sequences.services import next_value
from apps.stockmovements.services import Source, move_in, move_out, reverse_source

from .models import StockTransfer, StockTransferLine


@transaction.atomic
def create(workspace, *, from_warehouse, to_warehouse, transfer_date, rows, notes="", user=None) -> StockTransfer:
    if from_warehouse == to_warehouse:
        raise BusinessRuleError("Choose two different warehouses.")
    if not rows:
        raise BusinessRuleError("Add at least one product.")
    transfer = StockTransfer.objects.create(workspace=workspace, created_by=user, number=next_value(workspace, "stock_transfer"),
                                            from_warehouse=from_warehouse, to_warehouse=to_warehouse, transfer_date=transfer_date, notes=notes)
    source, total = Source("stock_transfer", transfer.pk, transfer.number), ZERO
    for row in rows:
        out = move_out(product=row["product"], warehouse=from_warehouse, quantity=row["quantity"], kind="transfer_out", source=source, date=transfer_date)
        move_in(product=row["product"], warehouse=to_warehouse, quantity=row["quantity"], unit_cost=out.unit_cost, kind="transfer_in",
                source=source, date=transfer_date)
        StockTransferLine.objects.create(transfer=transfer, product=row["product"], quantity=Decimal(row["quantity"]), unit_cost=out.unit_cost)
        total += -out.value
    transfer.total_value = total
    transfer.save(update_fields=["total_value", "updated_at"])
    return transfer


@transaction.atomic
def void(transfer: StockTransfer) -> StockTransfer:
    if transfer.status == StockTransfer.Status.VOID:
        raise BusinessRuleError("This transfer is already void.")
    reverse_source("stock_transfer", transfer.pk, transfer.transfer_date)
    transfer.status = StockTransfer.Status.VOID
    transfer.save(update_fields=["status", "updated_at"])
    return transfer
