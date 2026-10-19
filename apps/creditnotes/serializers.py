from rest_framework import serializers

from apps.core.dimensions import DimensionFields
from apps.core.fields import WorkspaceRelatedField
from apps.core.sales_serializers import ETIMS_FIELDS, SALES_DOCUMENT_FIELDS, SALES_READ_ONLY, SalesLineSerializer
from apps.customers.models import Customer
from apps.invoices.models import Invoice

from .models import CreditNote


class CreditNoteSerializer(DimensionFields, serializers.ModelSerializer):
    customer_id = WorkspaceRelatedField(Customer, source="customer", required=False)
    customer_name = serializers.CharField(source="customer.name", read_only=True)
    invoice_id = WorkspaceRelatedField(Invoice, source="invoice", allow_null=True, required=False)
    invoice_number = serializers.CharField(source="invoice.number", read_only=True, default=None)
    lines = SalesLineSerializer(many=True, required=False, help_text="Leave out to credit the whole invoice")

    class Meta:
        model = CreditNote
        fields = SALES_DOCUMENT_FIELDS + ETIMS_FIELDS + [
            "invoice_id", "invoice_number", "reason", "return_stock", "status", "applied_amount", "unapplied_amount", "void_reason",
        ]
        read_only_fields = SALES_READ_ONLY + ETIMS_FIELDS + ["invoice_number", "status", "applied_amount", "unapplied_amount", "void_reason"]
        extra_kwargs = {"currency": {"required": False}}


class CreditNoteVoidSerializer(serializers.Serializer):
    reason = serializers.CharField(max_length=255)
