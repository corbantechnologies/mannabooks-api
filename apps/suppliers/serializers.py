from rest_framework import serializers

from apps.core.fields import WorkspaceRelatedField
from apps.core.kra import clean_pin
from apps.taxrates.models import TaxRate

from .models import Supplier


class SupplierSerializer(serializers.ModelSerializer):
    balance = serializers.SerializerMethodField(help_text="What the business owes them now")
    withholding_tax_rate_id = WorkspaceRelatedField(TaxRate, source="withholding_tax_rate", allow_null=True, required=False)
    withholding_tax_rate_name = serializers.CharField(source="withholding_tax_rate.name", read_only=True, default=None)

    class Meta:
        model = Supplier
        fields = ["id", "number", "name", "kind", "email", "phone", "kra_pin", "address", "city", "payment_terms_days",
                  "withholding_tax_rate_id", "withholding_tax_rate_name", "bank_details", "notes", "is_active", "balance", "created_at"]
        read_only_fields = ["id", "number", "withholding_tax_rate_name", "balance", "created_at"]

    def get_balance(self, obj) -> str:
        if not hasattr(obj, "open_bills"):
            return "0.00"
        return str(obj.open_bills - obj.unallocated_payments)

    def validate_kra_pin(self, value):
        return clean_pin(value)

    def validate_withholding_tax_rate_id(self, rate):
        if rate is not None and rate.kind != "withholding_tax":
            raise serializers.ValidationError("Choose a withholding tax rate.")
        return rate


class SupplierStatementRowSerializer(serializers.Serializer):
    date = serializers.DateField()
    kind = serializers.ChoiceField(choices=["bill", "payment"])
    number = serializers.CharField()
    document_id = serializers.UUIDField()
    reference = serializers.CharField()
    billed = serializers.DecimalField(max_digits=18, decimal_places=2)
    paid = serializers.DecimalField(max_digits=18, decimal_places=2)
    balance = serializers.DecimalField(max_digits=18, decimal_places=2)


class SupplierStatementSerializer(serializers.Serializer):
    supplier = SupplierSerializer()
    opening_balance = serializers.DecimalField(max_digits=18, decimal_places=2)
    closing_balance = serializers.DecimalField(max_digits=18, decimal_places=2)
    rows = SupplierStatementRowSerializer(many=True)
