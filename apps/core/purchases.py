"""
Lines and totals shared by purchase documents (purchase and service orders, bills).

- `resolve_lines` checks request rows and fills defaults from the product: cost price, VAT rate, and
  the account (Inventory for stock items, Cost of goods sold for other goods; services need an account);
- `write_lines` saves the lines with net, VAT and total, and the document's totals.
"""
from dataclasses import dataclass
from decimal import Decimal

from django.db import transaction

from apps.core.exceptions import BusinessRuleError
from apps.core.money import ZERO, q2
from apps.core.sales import default_vat, price
from apps.ledgeraccounts.services import system_account


@dataclass
class PurchaseLineIn:
    description: str
    quantity: Decimal
    unit_cost: Decimal
    tax_rate: object
    account: object
    product: object = None
    extra: dict | None = None
    unit: str = ""
    unit_factor: Decimal = Decimal("1")


def resolve_lines(workspace, rows: list[dict], *, accounts: bool = True) -> list[PurchaseLineIn]:
    from apps.products.units import conversion

    if not rows:
        raise BusinessRuleError("Add at least one line.")
    fallback_vat = default_vat(workspace) if workspace.vat_registered else None
    lines = []
    for n, row in enumerate(rows, start=1):
        product = row.get("product")
        if product is not None and product.workspace_id != workspace.id:
            raise BusinessRuleError(f"Line {n}: that product belongs to another workspace.")
        quantity = Decimal(row.get("quantity") or 1)
        if quantity <= 0:
            raise BusinessRuleError(f"Line {n}: the quantity must be more than zero.")
        unit, factor, _ = conversion(product, row.get("unit"), n)
        unit_cost = row.get("unit_cost")
        unit_cost = Decimal(product.cost_price * factor if unit_cost is None and product is not None else unit_cost or 0)
        if unit_cost < 0:
            raise BusinessRuleError(f"Line {n}: the cost can't be negative.")
        tax_rate = row["tax_rate"] if "tax_rate" in row else (product.tax_rate if product and product.tax_rate_id else fallback_vat)
        if tax_rate is not None and (tax_rate.kind != "vat" or not tax_rate.is_active):
            raise BusinessRuleError(f"Line {n}: {tax_rate} can't be charged on a purchase line.")
        account = row.get("account")
        if account is None and accounts:
            if product is not None and product.track_inventory:
                account = system_account(workspace, "inventory")
            elif product is not None and product.kind == "goods":
                account = system_account(workspace, "cogs")
            else:
                raise BusinessRuleError(f"Line {n}: choose the expense account for this line.")
        allowed = account is not None and (account.account_type in ("asset", "expense") or account.system_key == "grni")
        if account is not None and (not allowed or not account.is_active):
            raise BusinessRuleError(f"Line {n}: record purchases in an active expense or asset account.")
        description = (row.get("description") or (product.name if product else "")).strip()
        if not description:
            raise BusinessRuleError(f"Line {n}: add a description.")
        lines.append(PurchaseLineIn(description=description[:255], quantity=quantity, unit_cost=unit_cost, tax_rate=tax_rate,
                                    account=account, product=product, extra=row.get("extra") or {}, unit=unit[:20], unit_factor=factor))
    return lines


@transaction.atomic
def write_lines(document, line_model, parent_field: str, lines: list[PurchaseLineIn]) -> list:
    """Replace the document's lines and recompute its totals. Returns the saved lines."""
    line_model.objects.filter(**{parent_field: document}).delete()
    subtotal = tax_total = total = ZERO
    objs = []
    for n, line in enumerate(lines, start=1):
        net, tax, gross = price(line.quantity, line.unit_cost, 0, line.tax_rate, document.prices_include_tax)
        subtotal, tax_total, total = subtotal + net, tax_total + tax, total + gross
        objs.append(line_model(**{parent_field: document}, product=line.product, description=line.description, quantity=line.quantity,
                               unit=line.unit, unit_factor=line.unit_factor,
                               unit_cost=line.unit_cost, tax_rate=line.tax_rate, account=line.account, net_amount=net, tax_amount=tax,
                               total_amount=gross, line_no=n, **(line.extra or {})))
    saved = line_model.objects.bulk_create(objs)
    document.subtotal, document.tax_total, document.total = subtotal, tax_total, total
    document.save(update_fields=["subtotal", "tax_total", "total", "updated_at"])
    return saved


def net_unit_cost(line) -> Decimal:
    """The line's cost per unit (the line's unit, e.g. a carton) before VAT."""
    return q2(line.net_amount / line.quantity) if line.quantity else ZERO


def net_stock_cost(line) -> Decimal:
    """The cost of one of the product's own unit before VAT (what stock is valued at)."""
    quantity = line.stock_quantity
    return (line.net_amount / quantity).quantize(Decimal("0.0001")) if quantity else ZERO
