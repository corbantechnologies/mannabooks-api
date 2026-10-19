from rest_framework import serializers

from apps.core.fields import WorkspaceRelatedField
from apps.customers.models import Customer
from apps.invoices.models import Invoice
from apps.ledgeraccounts.models import LedgerAccount

from .models import Payment, PaymentAllocation


class AllocationSerializer(serializers.ModelSerializer):
    invoice_id = WorkspaceRelatedField(Invoice, source="invoice")
    invoice_number = serializers.CharField(source="invoice.number", read_only=True)

    class Meta:
        model = PaymentAllocation
        fields = ["invoice_id", "invoice_number", "amount"]


class PaymentSerializer(serializers.ModelSerializer):
    customer_id = WorkspaceRelatedField(Customer, source="customer")
    customer_name = serializers.CharField(source="customer.name", read_only=True)
    deposit_account_id = WorkspaceRelatedField(LedgerAccount, source="deposit_account")
    deposit_account_name = serializers.CharField(source="deposit_account.name", read_only=True)
    allocations = AllocationSerializer(many=True, required=False)

    class Meta:
        model = Payment
        fields = [
            "id", "number", "customer_id", "customer_name", "payment_date", "amount", "method", "reference",
            "deposit_account_id", "deposit_account_name", "notes", "status", "unallocated_amount", "void_reason",
            "allocations", "created_at",
        ]
        read_only_fields = ["id", "number", "customer_name", "deposit_account_name", "status", "unallocated_amount", "void_reason", "created_at"]


class AllocateSerializer(serializers.Serializer):
    allocations = AllocationSerializer(many=True)


class PaymentVoidSerializer(serializers.Serializer):
    reason = serializers.CharField(max_length=255)
