from django.db import transaction
from django.utils import timezone

from apps.core import purchases
from apps.core.exceptions import BusinessRuleError
from apps.sequences.services import next_value

from .models import ServiceOrder, ServiceOrderLine

S = ServiceOrder.Status


@transaction.atomic
def save(workspace, *, header: dict, rows: list[dict] | None, user=None, order: ServiceOrder | None = None) -> ServiceOrder:
    if order is not None and order.status != S.DRAFT:
        raise BusinessRuleError("Only a draft order can be changed.")
    if order is None:
        if header.get("supplier") is None:
            raise BusinessRuleError("Choose a supplier.")
        order = ServiceOrder(workspace=workspace, created_by=user, number=next_value(workspace, "service_order"),
                             order_date=header.get("order_date") or timezone.localdate(), supplier=header["supplier"])
    for key, value in header.items():
        setattr(order, key, value)
    order.save()
    if rows is not None:
        purchases.write_lines(order, ServiceOrderLine, "service_order", purchases.resolve_lines(workspace, rows))
    return order


def act(order: ServiceOrder, action: str, user) -> ServiceOrder:
    if action == "approve":
        if order.status != S.DRAFT:
            raise BusinessRuleError("Only a draft order can be approved.")
        if order.total <= 0:
            raise BusinessRuleError("Add at least one line with a value first.")
        from apps.approvalrequests.services import gate

        if not gate("service_order", order, user):
            return order
        order.status, order.approved_by, order.approved_at = S.APPROVED, user, timezone.now()
    else:
        if order.status not in (S.DRAFT, S.APPROVED):
            raise BusinessRuleError("A completed order can't be cancelled.")
        order.status = S.CANCELLED
    order.save()
    return order
