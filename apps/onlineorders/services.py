"""
The online shop: what a workspace shows the public, taking orders, M-Pesa prompts for them, and turning a
completed order into a cash sale.
"""
import math
from decimal import Decimal

from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from apps.core.exceptions import BusinessRuleError
from apps.core.money import ZERO, q2

from .models import OnlineOrder

S = OnlineOrder.Status
MAX_LINES, MAX_QTY = 50, Decimal("1000")


def open_store(slug: str):
    from rest_framework.exceptions import NotFound

    from apps.workspaces.models import Workspace

    ws = Workspace.objects.filter(slug=slug, is_active=True, store_enabled=True).first()
    if ws is None:
        raise NotFound("This shop isn't open.")
    return ws


def mpesa_ready(workspace) -> bool:
    from apps.mpesaconnections.models import MpesaConnection

    return MpesaConnection.objects.filter(workspace=workspace, is_active=True).exists()


def _vat_rate(product, fallback):
    return product.tax_rate if product.tax_rate_id else fallback


def shop_price(product, fallback_vat) -> Decimal:
    """What the public pays for one: the selling price with VAT."""
    from apps.core.sales import price

    return price(Decimal(1), product.sale_price, 0, _vat_rate(product, fallback_vat), False)[2]


def _on_hand(products) -> dict:
    from apps.stockmovements.models import StockLevel

    rows = StockLevel.objects.filter(product__in=[p for p in products if p.track_inventory]).values("product").annotate(q=Sum("quantity"))
    return {r["product"]: r["q"] or ZERO for r in rows}


def catalogue(workspace) -> list[dict]:
    from apps.core.sales import default_vat
    from apps.products.models import Product

    products = list(Product.objects.filter(workspace=workspace, online=True, is_active=True).select_related("category", "tax_rate").order_by("name"))
    stock, vat = _on_hand(products), default_vat(workspace)
    return [{
        "id": p.pk, "name": p.name, "description": p.description, "category": p.category.name if p.category_id else "",
        "unit": p.unit, "price": shop_price(p, vat), "image_url": p.image_url,
        "available": (not p.track_inventory) or stock.get(p.pk, ZERO) > 0,
    } for p in products]


@transaction.atomic
def place(workspace, *, customer_name, phone, email="", fulfilment, address="", notes="", payment_method, rows) -> OnlineOrder:
    from apps.core.sales import default_vat
    from apps.mpesatransactions.services import normalise_phone
    from apps.products.models import Product
    from apps.sequences.services import next_value

    if not rows:
        raise BusinessRuleError("Your basket is empty.")
    if len(rows) > MAX_LINES:
        raise BusinessRuleError(f"An order can have up to {MAX_LINES} items.")
    if fulfilment == OnlineOrder.Fulfilment.DELIVERY and not workspace.store_allow_delivery:
        raise BusinessRuleError("This shop doesn't deliver. Choose pickup.")
    if fulfilment == OnlineOrder.Fulfilment.PICKUP and not workspace.store_allow_pickup:
        raise BusinessRuleError("This shop only delivers.")
    if fulfilment == OnlineOrder.Fulfilment.DELIVERY and not address.strip():
        raise BusinessRuleError("Enter where to deliver.")
    if payment_method == OnlineOrder.PaymentMethod.ON_DELIVERY and not workspace.store_pay_on_delivery:
        raise BusinessRuleError("This shop takes payment by M-Pesa when you order.")
    if payment_method == OnlineOrder.PaymentMethod.MPESA and not mpesa_ready(workspace):
        raise BusinessRuleError("This shop can't take M-Pesa online yet. Choose to pay on pickup or delivery.")
    phone = normalise_phone(phone)
    wanted = {}
    for row in rows:
        quantity = Decimal(str(row.get("quantity") or 0))
        if quantity <= 0 or quantity > MAX_QTY:
            raise BusinessRuleError("Each quantity must be between 1 and 1,000.")
        wanted[str(row["product_id"])] = wanted.get(str(row["product_id"]), ZERO) + quantity
    products = {str(p.pk): p for p in Product.objects.filter(workspace=workspace, online=True, is_active=True, pk__in=list(wanted))}
    if len(products) != len(wanted):
        raise BusinessRuleError("Something in your basket is no longer sold online. Refresh the shop and try again.")
    stock, vat = _on_hand(products.values()), default_vat(workspace)
    lines, subtotal = [], ZERO
    for pid, quantity in wanted.items():
        p = products[pid]
        if p.track_inventory and stock.get(p.pk, ZERO) < quantity:
            raise BusinessRuleError(f"Only {stock.get(p.pk, ZERO).normalize():f} {p.unit} of {p.name} left.")
        unit = shop_price(p, vat)
        total = q2(unit * quantity)
        lines.append({"product_id": pid, "name": p.name, "quantity": str(quantity), "unit": p.unit, "unit_price": str(unit), "total": str(total)})
        subtotal += total
    fee = workspace.store_delivery_fee if fulfilment == OnlineOrder.Fulfilment.DELIVERY else ZERO
    return OnlineOrder.objects.create(
        workspace=workspace, number=next_value(workspace, "online_order"), customer_name=customer_name.strip()[:150], phone=phone,
        email=email.strip(), fulfilment=fulfilment, address=address.strip(), notes=notes.strip()[:2000], lines=lines, subtotal=subtotal,
        delivery_fee=fee, total=subtotal + fee, payment_method=payment_method,
    )


def request_payment(order: OnlineOrder, phone: str | None = None) -> OnlineOrder:
    """An M-Pesa prompt for the order's total (rounded up to whole shillings, as M-Pesa needs)."""
    from apps.mpesatransactions.services import request_payment as stk

    if order.status in (S.COMPLETED, S.CANCELLED):
        raise BusinessRuleError(f"This order is {order.get_status_display().lower()}.")
    if order.payment_status == "paid":
        raise BusinessRuleError("This order is already paid.")
    tx = stk(order.workspace, phone=phone or order.phone, amount=Decimal(math.ceil(order.total)), reference=order.number)
    order.mpesa_transaction = tx
    order.save(update_fields=["mpesa_transaction", "updated_at"])
    return order


STEPS = {"confirm": ((S.NEW,), S.CONFIRMED), "ready": ((S.NEW, S.CONFIRMED), S.READY)}


def advance(order: OnlineOrder, action: str) -> OnlineOrder:
    sources, target = STEPS[action]
    if order.status not in sources:
        raise BusinessRuleError(f"A {order.get_status_display().lower()} order can't be marked {target.label.lower()}.")
    order.status = target
    order.save(update_fields=["status", "updated_at"])
    return order


def cancel(order: OnlineOrder, reason: str) -> OnlineOrder:
    if order.status in (S.COMPLETED, S.CANCELLED):
        raise BusinessRuleError(f"This order is already {order.get_status_display().lower()}.")
    if not reason.strip():
        raise BusinessRuleError("Say why, so you can tell the customer.")
    if order.payment_status == "paid":
        raise BusinessRuleError("The customer has paid by M-Pesa. Refund them first, then cancel.")
    order.status, order.cancel_reason = S.CANCELLED, reason.strip()[:255]
    order.save(update_fields=["status", "cancel_reason", "updated_at"])
    return order


@transaction.atomic
def complete(order: OnlineOrder, *, method: str = "", payment_reference: str = "", deposit_account=None, user=None) -> OnlineOrder:
    """
    Handed over: record the cash sale (which takes the stock out and posts the sale). A paid M-Pesa prompt is used as
    the payment; otherwise the shop says how the customer paid at pickup or delivery.
    """
    from apps.mpesatransactions.services import link_receipt
    from apps.products.models import Product
    from apps.receipts import services as receipts

    order = OnlineOrder.objects.select_for_update().get(pk=order.pk)
    if order.status in (S.COMPLETED, S.CANCELLED):
        raise BusinessRuleError(f"This order is already {order.get_status_display().lower()}.")
    paid = order.payment_status == "paid"
    if not paid and not method:
        raise BusinessRuleError("Say how the customer paid.")
    products = {str(p.pk): p for p in Product.objects.filter(workspace=order.workspace, pk__in=[ln["product_id"] for ln in order.lines])}
    rows = []
    for ln in order.lines:
        p = products.get(ln["product_id"])
        if p is None:
            raise BusinessRuleError(f"{ln['name']} was deleted. Record this sale by hand.")
        rows.append({"product": p, "quantity": Decimal(ln["quantity"])})  # at the product's price and VAT, as the shop showed
    if order.delivery_fee:
        rows.append({"description": "Delivery", "quantity": Decimal(1), "unit_price": order.delivery_fee, "tax_rate": None})
    receipt = receipts.create(
        order.workspace, header={"issue_date": timezone.localdate(), "reference": order.number, "notes": f"Online order {order.number}"},
        rows=rows, method="mpesa" if paid else method, deposit_account=deposit_account, payment_reference=payment_reference,
        customer_name=order.customer_name, mpesa_prompt=paid, user=user,
    )
    if paid:
        link_receipt(receipt, order.mpesa_transaction_id)
    order.receipt, order.status, order.completed_at = receipt, S.COMPLETED, timezone.now()
    order.save(update_fields=["receipt", "status", "completed_at", "updated_at"])
    return order
