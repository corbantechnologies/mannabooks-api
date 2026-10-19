from rest_framework import serializers

from apps.core.fields import WorkspaceRelatedField
from apps.customers.models import Customer
from apps.invoices.models import Invoice

from .models import MpesaTransaction


class MpesaTransactionSerializer(serializers.ModelSerializer):
    invoice_id = serializers.UUIDField(source="invoice.id", read_only=True, default=None)
    invoice_number = serializers.CharField(source="invoice.number", read_only=True, default=None)
    payment_id = serializers.UUIDField(source="payment.id", read_only=True, default=None)
    payment_number = serializers.CharField(source="payment.number", read_only=True, default=None)
    receipt_id = serializers.UUIDField(source="receipt.id", read_only=True, default=None)
    receipt_number = serializers.CharField(source="receipt.number", read_only=True, default=None)
    is_matched = serializers.BooleanField(read_only=True)

    class Meta:
        model = MpesaTransaction
        fields = [
            "id", "kind", "status", "phone", "payer_name", "amount", "mpesa_receipt", "account_reference", "result_description",
            "paid_at", "invoice_id", "invoice_number", "payment_id", "payment_number", "receipt_id", "receipt_number", "is_matched",
            "created_at",
        ]
        read_only_fields = fields


class PaymentPromptSerializer(serializers.Serializer):
    phone = serializers.CharField(max_length=20)
    amount = serializers.DecimalField(max_digits=18, decimal_places=2)
    invoice_id = WorkspaceRelatedField(Invoice, source="invoice", allow_null=True, required=False)
    reference = serializers.CharField(max_length=12, required=False, allow_blank=True)


class ApplyMpesaSerializer(serializers.Serializer):
    customer_id = WorkspaceRelatedField(Customer, source="customer")
    invoice_id = WorkspaceRelatedField(Invoice, source="invoice", allow_null=True, required=False)
