from rest_framework import serializers

from apps.core.fields import WorkspaceRelatedField
from apps.core.kra import clean_pin
from apps.pricelists.models import PriceList

from .models import Customer


class CustomerSerializer(serializers.ModelSerializer):
    balance = serializers.SerializerMethodField(help_text="What the customer owes now (negative: in credit)")
    price_list_id = WorkspaceRelatedField(PriceList, source="price_list", allow_null=True, required=False)
    price_list_name = serializers.CharField(source="price_list.name", read_only=True, default=None)

    class Meta:
        model = Customer
        fields = [
            "id", "number", "name", "kind", "email", "phone", "kra_pin", "address", "city", "currency",
            "payment_terms_days", "price_list_id", "price_list_name", "credit_limit", "notes", "is_active", "balance", "created_at",
        ]
        read_only_fields = ["id", "number", "balance", "price_list_name", "created_at"]

    def get_balance(self, obj) -> str:
        if not hasattr(obj, "open_invoices"):
            return "0.00"
        return str(obj.open_invoices - obj.unallocated_payments - obj.unapplied_credits)

    def validate_kra_pin(self, value):
        return clean_pin(value)

    def validate_currency(self, value):
        value = value.strip().upper()
        if value:
            from apps.currencies.models import Currency

            if not Currency.objects.filter(workspace=self.context["workspace"], code=value, is_active=True).exists():
                raise serializers.ValidationError("Switch this currency on in Currencies first.")
        return value


class StatementRowSerializer(serializers.Serializer):
    date = serializers.DateField()
    kind = serializers.ChoiceField(choices=["invoice", "payment", "credit_note"])
    number = serializers.CharField()
    document_id = serializers.UUIDField()
    debit = serializers.DecimalField(max_digits=18, decimal_places=2)
    credit = serializers.DecimalField(max_digits=18, decimal_places=2)
    balance = serializers.DecimalField(max_digits=18, decimal_places=2)


class StatementSerializer(serializers.Serializer):
    customer = CustomerSerializer()
    opening_balance = serializers.DecimalField(max_digits=18, decimal_places=2)
    closing_balance = serializers.DecimalField(max_digits=18, decimal_places=2)
    rows = StatementRowSerializer(many=True)
