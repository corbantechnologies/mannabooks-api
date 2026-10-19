from rest_framework import serializers

from apps.core.fields import WorkspaceRelatedField
from apps.customers.models import Customer
from apps.products.models import Product
from apps.taxrates.models import TaxRate

from .models import RecurringInvoice


class RecurringLineSerializer(serializers.Serializer):
    id = serializers.UUIDField(read_only=True)
    product_id = WorkspaceRelatedField(Product, source="product", allow_null=True, required=False)
    description = serializers.CharField(max_length=255, required=False, allow_blank=True)
    quantity = serializers.DecimalField(max_digits=14, decimal_places=3, default=1)
    unit_price = serializers.DecimalField(max_digits=18, decimal_places=4, required=False, allow_null=True)
    discount_percent = serializers.DecimalField(max_digits=5, decimal_places=2, default=0)
    tax_rate_id = WorkspaceRelatedField(TaxRate, source="tax_rate", allow_null=True, required=False)


class RecurringInvoiceSerializer(serializers.ModelSerializer):
    customer_id = WorkspaceRelatedField(Customer, source="customer")
    customer_name = serializers.CharField(source="customer.name", read_only=True)
    last_invoice_id = serializers.UUIDField(source="last_invoice.id", read_only=True, default=None)
    last_invoice_number = serializers.CharField(source="last_invoice.number", read_only=True, default=None)
    lines = RecurringLineSerializer(many=True, required=False)

    class Meta:
        model = RecurringInvoice
        fields = [
            "id", "name", "customer_id", "customer_name", "frequency", "start_date", "next_run_date", "end_date", "auto_issue",
            "prices_include_tax", "reference", "notes", "status", "invoices_created", "last_invoice_id", "last_invoice_number",
            "last_error", "lines", "created_at",
        ]
        read_only_fields = ["id", "customer_name", "next_run_date", "status", "invoices_created", "last_invoice_id",
                            "last_invoice_number", "last_error", "created_at"]


class RecurringActionSerializer(serializers.Serializer):
    action = serializers.ChoiceField(choices=["pause", "resume", "end", "run"])
