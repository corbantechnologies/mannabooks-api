from decimal import Decimal

from apps.core.money import q2

from .models import PriceList, PriceListItem


def price_for(product, price_list: PriceList | None) -> Decimal:
    """What `product` sells for on `price_list` (its normal price without one)."""
    if price_list is None or not price_list.is_active:
        return product.sale_price
    item = PriceListItem.objects.filter(price_list=price_list, product=product).first()
    if item is not None:
        return item.price
    return q2(product.sale_price * (1 + price_list.adjust_percent / Decimal(100)))


def prices_for(workspace, price_list: PriceList | None) -> dict[str, Decimal]:
    """Every active product's price on `price_list`, keyed by product id."""
    from apps.products.models import Product

    products = Product.objects.filter(workspace=workspace, is_active=True).only("id", "sale_price")
    if price_list is None or not price_list.is_active:
        return {str(p.id): p.sale_price for p in products}
    items = dict(PriceListItem.objects.filter(price_list=price_list).values_list("product_id", "price"))
    factor = 1 + price_list.adjust_percent / Decimal(100)
    return {str(p.id): items.get(p.id, q2(p.sale_price * factor)) for p in products}
