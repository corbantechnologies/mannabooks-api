from rest_framework import serializers

from apps.core.fields import WorkspaceRelatedField
from apps.customers.models import Customer
from apps.invoices.models import Invoice
from apps.products.models import Product

from .models import DeliveryNote


class DeliveryNoteLineSerializer(serializers.Serializer):
    id = serializers.UUIDField(read_only=True)
    product_id = WorkspaceRelatedField(Product, source="product", allow_null=True, required=False)
    description = serializers.CharField(max_length=255, required=False, allow_blank=True)
    quantity = serializers.DecimalField(max_digits=14, decimal_places=3)
    unit = serializers.CharField(max_length=20, required=False, allow_blank=True)


class DeliveryNoteSerializer(serializers.ModelSerializer):
    customer_id = WorkspaceRelatedField(Customer, source="customer", required=False)
    customer_name = serializers.CharField(source="customer.name", read_only=True)
    invoice_id = WorkspaceRelatedField(Invoice, source="invoice", allow_null=True, required=False)
    invoice_number = serializers.CharField(source="invoice.number", read_only=True, default=None)
    lines = DeliveryNoteLineSerializer(many=True, required=False)

    class Meta:
        model = DeliveryNote
        fields = [
            "id", "number", "customer_id", "customer_name", "invoice_id", "invoice_number", "delivery_date", "status",
            "delivery_address", "contact_person", "contact_phone", "vehicle", "driver", "notes", "received_by",
            "dispatched_at", "delivered_at", "lines", "created_at",
        ]
        read_only_fields = ["id", "number", "customer_name", "invoice_number", "status", "received_by", "dispatched_at",
                            "delivered_at", "created_at"]
        extra_kwargs = {"delivery_date": {"required": False}}


class DeliveryActionSerializer(serializers.Serializer):
    action = serializers.ChoiceField(choices=["dispatch", "deliver", "void"])
    received_by = serializers.CharField(max_length=120, required=False, allow_blank=True)
