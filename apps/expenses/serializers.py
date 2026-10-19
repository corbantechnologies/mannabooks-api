from rest_framework import serializers

from apps.bankaccounts.models import BankAccount
from apps.core.dimensions import DIMENSION_FIELDS, DimensionFields
from apps.core.fields import WorkspaceRelatedField
from apps.core.purchase_serializers import PurchaseLineSerializer
from apps.suppliers.models import Supplier

from .models import Expense


class ExpenseSerializer(DimensionFields, serializers.ModelSerializer):
    paid_from_id = WorkspaceRelatedField(BankAccount, source="paid_from")
    paid_from_name = serializers.CharField(source="paid_from.name", read_only=True)
    supplier_id = WorkspaceRelatedField(Supplier, source="supplier", allow_null=True, required=False)
    supplier_name = serializers.CharField(source="supplier.name", read_only=True, default=None)
    lines = PurchaseLineSerializer(many=True)

    class Meta:
        model = Expense
        fields = ["id", "number", "expense_date", "paid_from_id", "paid_from_name", "payee", "supplier_id", "supplier_name", "method", "reference",
                  "supplier_etims_number", "prices_include_tax", "subtotal", "tax_total", "total", "notes", "status", "void_reason", "lines", "created_at", *DIMENSION_FIELDS]
        read_only_fields = ["id", "number", "paid_from_name", "supplier_name", "subtotal", "tax_total", "total", "status", "void_reason", "created_at"]
        extra_kwargs = {"expense_date": {"required": False}}


class ExpenseVoidSerializer(serializers.Serializer):
    reason = serializers.CharField(max_length=255)
