from django.db import transaction
from django.utils import timezone

from apps.core import purchases
from apps.core.exceptions import BusinessRuleError
from apps.sequences.services import next_value

from .models import PurchaseOrder, PurchaseOrderLine

S = PurchaseOrder.Status


@transaction.atomic
def save(workspace, *, header: dict, rows: list[dict] | None, user=None, order: PurchaseOrder | None = None) -> PurchaseOrder:
    if order is not None and order.status != S.DRAFT:
        raise BusinessRuleError("Only a draft order can be changed.")
    if order is None:
        if header.get("supplier") is None:
            raise BusinessRuleError("Choose a supplier.")
        order = PurchaseOrder(workspace=workspace, created_by=user, number=next_value(workspace, "purchase_order"),
                              order_date=header.get("order_date") or timezone.localdate(), supplier=header["supplier"])
    for key, value in header.items():
        setattr(order, key, value)
    if not order.supplier.is_active:
        raise BusinessRuleError(f"{order.supplier} is inactive.")
    if order.expected_date and order.expected_date < order.order_date:
        raise BusinessRuleError("The expected date can't be before the order date.")
    order.save()
    if rows is not None:
        purchases.write_lines(order, PurchaseOrderLine, "purchase_order", purchases.resolve_lines(workspace, rows, accounts=False))
    return order


def approve(order: PurchaseOrder, user) -> PurchaseOrder:
    if order.status != S.DRAFT:
        raise BusinessRuleError("Only a draft order can be approved.")
    if not order.lines.exists() or order.total <= 0:
        raise BusinessRuleError("Add at least one line with a value first.")
    from apps.approvalrequests.services import gate

    if not gate("purchase_order", order, user):
        return order
    order.status, order.approved_by, order.approved_at = S.APPROVED, user, timezone.now()
    order.save(update_fields=["status", "approved_by", "approved_at", "updated_at"])
    return order


def cancel(order: PurchaseOrder) -> PurchaseOrder:
    if order.status not in (S.DRAFT, S.APPROVED):
        raise BusinessRuleError("Goods have been received on this order. Close it instead.")
    order.status = S.CANCELLED
    order.save(update_fields=["status", "updated_at"])
    return order


def close(order: PurchaseOrder) -> PurchaseOrder:
    """Stop waiting for the rest of a partly received order."""
    if order.status not in (S.APPROVED, S.PARTIALLY_RECEIVED):
        raise BusinessRuleError("Only an approved, partly received order can be closed.")
    order.status = S.CLOSED
    order.save(update_fields=["status", "updated_at"])
    return order


def refresh_received(order: PurchaseOrder) -> None:
    if order.status in (S.DRAFT, S.CANCELLED, S.CLOSED):
        return
    lines = list(order.lines.all())
    if all(line.received_quantity >= line.quantity for line in lines):
        order.status = S.RECEIVED
    elif any(line.received_quantity > 0 for line in lines):
        order.status = S.PARTIALLY_RECEIVED
    else:
        order.status = S.APPROVED
    order.save(update_fields=["status", "updated_at"])
