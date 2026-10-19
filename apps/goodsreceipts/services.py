from decimal import Decimal

from django.db import transaction

from apps.core.exceptions import BusinessRuleError
from apps.core.money import ZERO, q2
from apps.core.purchases import net_unit_cost
from apps.journals.services import LineInput, replace_for_source
from apps.ledgeraccounts.services import system_account
from apps.purchaseorders.models import PurchaseOrder, PurchaseOrderLine
from apps.purchaseorders.services import refresh_received
from apps.sequences.services import next_value
from apps.stockmovements.services import Source, move_in, reverse_source

from .models import GoodsReceipt, GoodsReceiptLine

SOURCE = {"source": "goods_receipt", "source_model": "goodsreceipts.GoodsReceipt"}


def _post(grn, user=None):
    value = sum((line.value for line in grn.lines.all() if line.stocked), ZERO)
    lines = []
    if value:
        label = f"Goods received {grn.number}"
        lines = [LineInput(account=system_account(grn.workspace, "inventory"), debit=value, description=label),
                 LineInput(account=system_account(grn.workspace, "grni"), credit=value, description=label)]
    replace_for_source(grn.workspace, **SOURCE, source_id=str(grn.pk), entry_date=grn.receipt_date, reference=grn.number,
                       description=f"Goods received {grn.number} from {grn.supplier}", lines=lines, user=user)


@transaction.atomic
def receive(workspace, *, supplier=None, purchase_order: PurchaseOrder | None = None, warehouse=None, receipt_date, rows: list[dict],
            delivery_note_number="", notes="", user=None) -> GoodsReceipt:
    """
    rows: [{"order_line": PurchaseOrderLine, "quantity": n}] against an order, or [{"product", "quantity", "unit_cost"}] without one.
    """
    from apps.warehouses.services import default_warehouse

    if purchase_order is not None:
        purchase_order = PurchaseOrder.objects.select_for_update().get(pk=purchase_order.pk)
        if purchase_order.status not in (PurchaseOrder.Status.APPROVED, PurchaseOrder.Status.PARTIALLY_RECEIVED):
            raise BusinessRuleError(f"Order {purchase_order.number} is {purchase_order.get_status_display().lower()}; goods can't be received on it.")
        supplier = purchase_order.supplier
        warehouse = warehouse or purchase_order.warehouse
    if supplier is None:
        raise BusinessRuleError("Choose the supplier or the purchase order.")
    warehouse = warehouse or default_warehouse(workspace)
    grn = GoodsReceipt.objects.create(workspace=workspace, created_by=user, number=next_value(workspace, "goods_receipt"), supplier=supplier,
                                      purchase_order=purchase_order, warehouse=warehouse, receipt_date=receipt_date,
                                      delivery_note_number=delivery_note_number, notes=notes)
    source, total, n = Source("goods_receipt", grn.pk, grn.number), ZERO, 0
    for row in rows:
        quantity = Decimal(row.get("quantity") or 0)
        if quantity <= 0:
            continue
        order_line = row.get("order_line")
        if order_line is not None:
            order_line = PurchaseOrderLine.objects.select_for_update().get(pk=order_line.pk)
            if purchase_order is None or order_line.purchase_order_id != purchase_order.pk:
                raise BusinessRuleError("A line belongs to another order.")
            outstanding = order_line.quantity - order_line.received_quantity
            if quantity > outstanding:
                raise BusinessRuleError(f"{order_line.description}: only {outstanding.normalize():f} still to receive.")
            product, unit_cost, description = order_line.product, net_unit_cost(order_line), order_line.description
            order_line.received_quantity += quantity
            order_line.save(update_fields=["received_quantity", "updated_at"])
        else:
            if purchase_order is not None:
                raise BusinessRuleError("Receive against the order's lines.")
            product, unit_cost = row.get("product"), Decimal(row.get("unit_cost") if row.get("unit_cost") is not None else 0)
            description = product.name if product else ""
            if product is not None and row.get("unit_cost") is None:
                unit_cost = product.cost_price
        if product is None or product.kind != "goods":
            raise BusinessRuleError("Only goods (products) can be received. Record services on a service order.")
        n += 1
        line = GoodsReceiptLine.objects.create(goods_receipt=grn, order_line=order_line, product=product, description=description,
                                               quantity=quantity, unit_cost=unit_cost, value=q2(quantity * unit_cost),
                                               stocked=product.track_inventory, line_no=n)
        if line.stocked:
            move_in(product=product, warehouse=warehouse, quantity=quantity, unit_cost=unit_cost, kind="purchase", source=source, date=receipt_date)
        total += line.value
    if n == 0:
        raise BusinessRuleError("Enter the quantity received on at least one line.")
    grn.total_value = total
    grn.save(update_fields=["total_value", "updated_at"])
    _post(grn, user)
    if purchase_order is not None:
        refresh_received(purchase_order)
    return grn


@transaction.atomic
def void(grn: GoodsReceipt, reason: str, user=None) -> GoodsReceipt:
    if grn.status == GoodsReceipt.Status.VOID:
        raise BusinessRuleError("This delivery is already void.")
    if grn.lines.filter(billed_quantity__gt=0).exists():
        raise BusinessRuleError("The supplier's bill for these goods is recorded. Void the bill first.")
    reverse_source("goods_receipt", grn.pk, grn.receipt_date)
    replace_for_source(grn.workspace, **SOURCE, source_id=str(grn.pk), entry_date=grn.receipt_date, description="", lines=[], user=user)
    for line in grn.lines.select_related("order_line"):
        if line.order_line_id:
            PurchaseOrderLine.objects.filter(pk=line.order_line_id).update(received_quantity=line.order_line.received_quantity - line.quantity)
    grn.status, grn.void_reason = GoodsReceipt.Status.VOID, reason[:255]
    grn.save(update_fields=["status", "void_reason", "updated_at"])
    if grn.purchase_order_id:
        refresh_received(grn.purchase_order)
    return grn
