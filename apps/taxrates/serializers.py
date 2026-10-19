from rest_framework import serializers

from apps.ledgeraccounts.models import LedgerAccount

from .models import TaxRate


class TaxRateSerializer(serializers.ModelSerializer):
    sales_account_id = serializers.PrimaryKeyRelatedField(
        source="sales_account", queryset=LedgerAccount.objects.none(), allow_null=True, required=False
    )
    purchases_account_id = serializers.PrimaryKeyRelatedField(
        source="purchases_account", queryset=LedgerAccount.objects.none(), allow_null=True, required=False
    )
    sales_account_name = serializers.SerializerMethodField()
    purchases_account_name = serializers.SerializerMethodField()

    class Meta:
        model = TaxRate
        fields = [
            "id", "code", "name", "kind", "rate", "etims_code", "sales_account_id", "sales_account_name",
            "purchases_account_id", "purchases_account_name", "is_default", "is_active",
        ]
        read_only_fields = ["id", "sales_account_name", "purchases_account_name"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        workspace = self.context.get("workspace")
        if workspace is not None:
            accounts = LedgerAccount.objects.filter(workspace=workspace)
            self.fields["sales_account_id"].queryset = accounts
            self.fields["purchases_account_id"].queryset = accounts

    def get_sales_account_name(self, obj) -> str | None:
        return str(obj.sales_account) if obj.sales_account else None

    def get_purchases_account_name(self, obj) -> str | None:
        return str(obj.purchases_account) if obj.purchases_account else None

    def validate_code(self, value):
        value = value.strip().upper()
        clash = TaxRate.objects.filter(workspace=self.context["workspace"], code=value)
        if self.instance:
            clash = clash.exclude(pk=self.instance.pk)
        if clash.exists():
            raise serializers.ValidationError("Another tax rate uses this code.")
        return value

    def validate_rate(self, value):
        if value < 0 or value > 100:
            raise serializers.ValidationError("Enter a percentage between 0 and 100.")
        return value

    def validate(self, attrs):
        rate = attrs.get("rate", getattr(self.instance, "rate", 0))
        kind = attrs.get("kind", getattr(self.instance, "kind", "vat"))
        sales = attrs.get("sales_account", getattr(self.instance, "sales_account", None))
        if rate and rate > 0 and sales is None:
            raise serializers.ValidationError({"sales_account_id": ["Choose the account this tax is posted to."]})
        if kind != "vat" and attrs.get("is_default"):
            raise serializers.ValidationError({"is_default": ["Only a VAT rate can be the default."]})
        return attrs
