from rest_framework import serializers

from apps.core.dimensions import DIMENSION_FIELDS
from apps.core.fields import WorkspaceRelatedField
from apps.ledgeraccounts.models import LedgerAccount
from apps.products.models import Product
from apps.taxrates.models import TaxRate


class PurchaseLineSerializer(serializers.Serializer):
    """One purchase line. Leave out the cost, VAT or account to use the product's."""

    id = serializers.UUIDField(read_only=True)
    product_id = WorkspaceRelatedField(Product, source="product", allow_null=True, required=False)
    product_tracked = serializers.BooleanField(source="product.track_inventory", read_only=True, default=False)
    description = serializers.CharField(max_length=255, required=False, allow_blank=True)
    quantity = serializers.DecimalField(max_digits=14, decimal_places=3)
    unit = serializers.CharField(max_length=20, required=False, allow_blank=True,
                                 help_text="Blank: the product's own unit. Another unit must be one of the product's other units.")
    unit_factor = serializers.DecimalField(max_digits=14, decimal_places=4, read_only=True)
    unit_cost = serializers.DecimalField(max_digits=18, decimal_places=4, required=False)
    tax_rate_id = WorkspaceRelatedField(TaxRate, source="tax_rate", allow_null=True, required=False)
    tax_rate_name = serializers.CharField(source="tax_rate.name", read_only=True, default=None)
    account_id = WorkspaceRelatedField(LedgerAccount, source="account", allow_null=True, required=False)
    account_name = serializers.CharField(source="account.name", read_only=True, default=None)
    net_amount = serializers.DecimalField(max_digits=18, decimal_places=2, read_only=True)
    tax_amount = serializers.DecimalField(max_digits=18, decimal_places=2, read_only=True)
    total_amount = serializers.DecimalField(max_digits=18, decimal_places=2, read_only=True)


PURCHASE_FIELDS = ["id", "number", "supplier_id", "supplier_name", "prices_include_tax", "reference", "notes", "subtotal", "tax_total",
                   "total", "lines", "created_at", *DIMENSION_FIELDS]
PURCHASE_READ_ONLY = ["id", "number", "supplier_name", "subtotal", "tax_total", "total", "created_at"]


def rows_from(lines: list[dict]) -> list[dict]:
    """Request lines without the keys the client left out (so product defaults apply)."""
    return [dict(line) for line in lines]
