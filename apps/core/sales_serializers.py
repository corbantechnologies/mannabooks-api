from rest_framework import serializers

from apps.core.dimensions import DIMENSION_FIELDS
from apps.core.fields import WorkspaceRelatedField
from apps.ledgeraccounts.models import LedgerAccount
from apps.products.models import Product
from apps.taxrates.models import TaxRate


class SalesLineSerializer(serializers.Serializer):
    """One line of a sales document. Leave out price, VAT or account to use the product's defaults."""

    id = serializers.UUIDField(read_only=True)
    product_id = WorkspaceRelatedField(Product, source="product", allow_null=True, required=False)
    description = serializers.CharField(max_length=255, required=False, allow_blank=True)
    quantity = serializers.DecimalField(max_digits=14, decimal_places=3, default=1)
    unit_price = serializers.DecimalField(max_digits=18, decimal_places=4, required=False)
    discount_percent = serializers.DecimalField(max_digits=5, decimal_places=2, default=0)
    discount_amount = serializers.DecimalField(max_digits=18, decimal_places=2, default=0)
    tax_rate_id = WorkspaceRelatedField(TaxRate, source="tax_rate", allow_null=True, required=False)
    account_id = WorkspaceRelatedField(LedgerAccount, source="account", required=False)
    tax_rate_name = serializers.CharField(source="tax_rate.name", read_only=True, default=None)
    account_name = serializers.CharField(source="account.name", read_only=True)
    net_amount = serializers.DecimalField(max_digits=18, decimal_places=2, read_only=True)
    tax_amount = serializers.DecimalField(max_digits=18, decimal_places=2, read_only=True)
    total_amount = serializers.DecimalField(max_digits=18, decimal_places=2, read_only=True)


SALES_DOCUMENT_FIELDS = [
    "id", "number", "customer_id", "customer_name", "issue_date", "currency", "exchange_rate", "prices_include_tax",
    "reference", "notes", "subtotal", "tax_total", "total", "lines", "created_at", *DIMENSION_FIELDS,
]
SALES_READ_ONLY = ["id", "number", "customer_name", "exchange_rate", "subtotal", "tax_total", "total", "created_at"]
ETIMS_FIELDS = ["etims_status", "etims_cu_invoice_number", "etims_signature", "etims_qr_url", "etims_signed_at"]
