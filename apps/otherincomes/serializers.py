from rest_framework import serializers

from apps.bankaccounts.models import BankAccount
from apps.core.dimensions import DIMENSION_FIELDS, DimensionFields
from apps.core.fields import WorkspaceRelatedField
from apps.ledgeraccounts.models import LedgerAccount
from apps.taxrates.models import TaxRate

from .models import OtherIncome


class IncomeLineSerializer(serializers.Serializer):
    id = serializers.UUIDField(read_only=True)
    description = serializers.CharField(max_length=255, required=False, allow_blank=True)
    account_id = WorkspaceRelatedField(LedgerAccount, source="account", allow_null=True, required=False)
    account_name = serializers.CharField(source="account.name", read_only=True)
    tax_rate_id = WorkspaceRelatedField(TaxRate, source="tax_rate", allow_null=True, required=False)
    amount = serializers.DecimalField(max_digits=18, decimal_places=2)
    net_amount = serializers.DecimalField(max_digits=18, decimal_places=2, read_only=True)
    tax_amount = serializers.DecimalField(max_digits=18, decimal_places=2, read_only=True)


class OtherIncomeSerializer(DimensionFields, serializers.ModelSerializer):
    received_into_id = WorkspaceRelatedField(BankAccount, source="received_into")
    received_into_name = serializers.CharField(source="received_into.name", read_only=True)
    lines = IncomeLineSerializer(many=True)

    class Meta:
        model = OtherIncome
        fields = ["id", "number", "income_date", "received_into_id", "received_into_name", "payer", "reference", "prices_include_tax", "subtotal",
                  "tax_total", "total", "notes", "status", "void_reason", "lines", "created_at", *DIMENSION_FIELDS]
        read_only_fields = ["id", "number", "received_into_name", "subtotal", "tax_total", "total", "status", "void_reason", "created_at"]
        extra_kwargs = {"income_date": {"required": False}}


class IncomeVoidSerializer(serializers.Serializer):
    reason = serializers.CharField(max_length=255)
