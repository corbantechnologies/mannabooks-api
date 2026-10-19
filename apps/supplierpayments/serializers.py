from rest_framework import serializers

from apps.bills.models import Bill
from apps.core.fields import WorkspaceRelatedField
from apps.ledgeraccounts.models import LedgerAccount
from apps.suppliers.models import Supplier

from .models import SupplierPayment


class SupplierAllocationSerializer(serializers.Serializer):
    bill_id = WorkspaceRelatedField(Bill, source="bill")
    bill_number = serializers.CharField(source="bill.supplier_invoice_number", read_only=True)
    amount = serializers.DecimalField(max_digits=18, decimal_places=2)


class SupplierPaymentSerializer(serializers.ModelSerializer):
    supplier_id = WorkspaceRelatedField(Supplier, source="supplier")
    supplier_name = serializers.CharField(source="supplier.name", read_only=True)
    paid_from_id = WorkspaceRelatedField(LedgerAccount, source="paid_from")
    paid_from_name = serializers.CharField(source="paid_from.name", read_only=True)
    allocations = SupplierAllocationSerializer(many=True, required=False)

    class Meta:
        model = SupplierPayment
        fields = ["id", "number", "supplier_id", "supplier_name", "payment_date", "amount", "withholding_amount", "method", "reference",
                  "paid_from_id", "paid_from_name", "notes", "status", "unallocated_amount", "void_reason", "allocations", "created_at"]
        read_only_fields = ["id", "number", "supplier_name", "paid_from_name", "status", "unallocated_amount", "void_reason", "created_at"]


class SupplierPaymentVoidSerializer(serializers.Serializer):
    reason = serializers.CharField(max_length=255)
