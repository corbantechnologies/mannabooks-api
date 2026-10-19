"""
Pricing and posting shared by every sales document.

- `resolve_lines` turns request rows into checked lines, filling defaults from the product (price,
  VAT rate, income account) and the workspace (default VAT rate);
- `price` computes a line's net, VAT and total, with prices either excluding or including VAT;
- `write_lines` saves a document's lines and its totals;
- `posting_lines` builds the journal lines for a document, converted to the base currency.
"""
from dataclasses import dataclass
from decimal import Decimal

from django.db import transaction

from apps.core.exceptions import BusinessRuleError
from apps.core.money import ZERO, q2
from apps.journals.services import LineInput
from apps.ledgeraccounts.models import LedgerAccount
from apps.ledgeraccounts.services import system_account
from apps.products.models import Product
from apps.taxrates.models import TaxRate

HUNDRED = Decimal("100")


@dataclass
class LineIn:
    description: str
    quantity: Decimal
    unit_price: Decimal
    discount_percent: Decimal
    tax_rate: TaxRate | None
    account: LedgerAccount
    product: Product | None = None
    discount_amount: Decimal = ZERO


def price(quantity, unit_price, discount_percent, tax_rate, prices_include_tax, discount_amount=ZERO) -> tuple[Decimal, Decimal, Decimal]:
    """(net, VAT, total) for one line, each rounded to cents. `discount_amount` comes off after the percentage."""
    amount = q2(Decimal(quantity) * Decimal(unit_price) * (1 - Decimal(discount_percent) / HUNDRED))
    amount = max(amount - q2(discount_amount), ZERO)
    rate = (tax_rate.rate / HUNDRED) if tax_rate is not None and tax_rate.kind == "vat" else ZERO
    if prices_include_tax:
        total = amount
        net = q2(total / (1 + rate))
        return net, total - net, total
    tax = q2(amount * rate)
    return amount, tax, amount + tax


def default_vat(workspace) -> TaxRate | None:
    return TaxRate.objects.filter(workspace=workspace, kind="vat", is_default=True, is_active=True).first()


def resolve_lines(workspace, rows: list[dict], customer=None) -> list[LineIn]:
    """Checked lines. A product without a price takes the customer's price-list price (or its normal price)."""
    from apps.pricelists.services import price_for

    if not rows:
        raise BusinessRuleError("Add at least one line.")
    fallback_vat = default_vat(workspace)
    price_list = getattr(customer, "price_list", None)
    lines = []
    for n, row in enumerate(rows, start=1):
        product = row.get("product")
        if product is not None and product.workspace_id != workspace.id:
            raise BusinessRuleError(f"Line {n}: that product belongs to another workspace.")
        quantity = Decimal(row.get("quantity") or 1)
        unit_price = row.get("unit_price")
        if unit_price is None:
            if product is None:
                raise BusinessRuleError(f"Line {n}: enter a price.")
            unit_price = price_for(product, price_list)
        unit_price = Decimal(unit_price)
        discount_amount = q2(row.get("discount_amount") or 0)
        if discount_amount < 0:
            raise BusinessRuleError(f"Line {n}: the discount can't be negative.")
        discount = Decimal(row.get("discount_percent") or 0)
        if quantity <= 0:
            raise BusinessRuleError(f"Line {n}: the quantity must be more than zero.")
        if unit_price < 0:
            raise BusinessRuleError(f"Line {n}: the price can't be negative.")
        if not (ZERO <= discount <= HUNDRED):
            raise BusinessRuleError(f"Line {n}: the discount must be between 0% and 100%.")
        if "tax_rate" in row:
            tax_rate = row["tax_rate"]
        else:
            tax_rate = product.tax_rate if product and product.tax_rate_id else fallback_vat
        if tax_rate is not None and (tax_rate.kind != "vat" or not tax_rate.is_active):
            raise BusinessRuleError(f"Line {n}: {tax_rate} can't be charged on a sales line.")
        account = row.get("account") or (product.income_account if product and product.income_account_id else None)
        if account is None:
            key = "service_income" if product is not None and product.kind == "service" else "sales"
            account = system_account(workspace, key)
        if account.account_type != "income" or not account.is_active:
            raise BusinessRuleError(f"Line {n}: sales must be recorded in an active income account.")
        description = (row.get("description") or (product.name if product else "")).strip()
        if not description:
            raise BusinessRuleError(f"Line {n}: add a description.")
        lines.append(LineIn(description=description[:255], quantity=quantity, unit_price=unit_price,
                            discount_percent=discount, tax_rate=tax_rate, account=account, product=product,
                            discount_amount=discount_amount))
    return lines


@transaction.atomic
def write_lines(document, line_model, parent_field: str, lines: list[LineIn]) -> None:
    """Replace the document's lines and recompute its totals."""
    line_model.objects.filter(**{parent_field: document}).delete()
    subtotal = tax_total = total = ZERO
    objs = []
    for n, line in enumerate(lines, start=1):
        net, tax, gross = price(line.quantity, line.unit_price, line.discount_percent, line.tax_rate, document.prices_include_tax,
                                line.discount_amount)
        subtotal, tax_total, total = subtotal + net, tax_total + tax, total + gross
        objs.append(line_model(
            **{parent_field: document}, product=line.product, description=line.description, quantity=line.quantity,
            unit_price=line.unit_price, discount_percent=line.discount_percent, discount_amount=line.discount_amount, tax_rate=line.tax_rate,
            account=line.account, net_amount=net, tax_amount=tax, total_amount=gross, line_no=n,
        ))
    line_model.objects.bulk_create(objs)
    document.subtotal, document.tax_total, document.total = subtotal, tax_total, total
    document.save(update_fields=["subtotal", "tax_total", "total", "updated_at"])


def posting_lines(document, lines, counter_account, *, label: str, credit_income: bool = True) -> list[LineInput]:
    """
    Journal lines for a sales document in the base currency: income and VAT on one side, the counter
    account (receivable, cash or bank) on the other. `credit_income=False` mirrors it (credit notes).
    """
    rate = Decimal(document.exchange_rate or 1)
    income: dict = {}
    vat: dict = {}
    for line in lines:
        income[line.account] = income.get(line.account, ZERO) + q2(line.net_amount * rate)
        if line.tax_amount:
            if line.tax_rate is None or line.tax_rate.sales_account is None:
                raise BusinessRuleError(f"{line.tax_rate} has no account for tax on sales. Set it in Tax rates.")
            account = line.tax_rate.sales_account
            vat[account] = vat.get(account, ZERO) + q2(line.tax_amount * rate)
    parts = [(a, amt, f"{label} sales") for a, amt in income.items() if amt] + [(a, amt, f"{label} VAT") for a, amt in vat.items() if amt]
    counter_total = sum((amt for _, amt, _ in parts), ZERO)
    side = (lambda amt: {"credit": amt}) if credit_income else (lambda amt: {"debit": amt})
    other = (lambda amt: {"debit": amt}) if credit_income else (lambda amt: {"credit": amt})
    result = [LineInput(account=counter_account, description=label, **other(counter_total))]
    result += [LineInput(account=a, description=d, **side(amt)) for a, amt, d in parts]
    return result


def document_rate(workspace, currency: str, on_date) -> Decimal:
    from apps.exchangerates.services import rate_on

    return rate_on(workspace, currency, on_date)
