from rest_framework import serializers

from apps.core.fields import WorkspaceRelatedField
from apps.ledgeraccounts.models import LedgerAccount
from apps.taxrates.models import TaxRate

from .models import ProductCategory


class ProductCategorySerializer(serializers.ModelSerializer):
    parent_id = WorkspaceRelatedField(ProductCategory, source="parent", allow_null=True, required=False)
    parent_name = serializers.CharField(source="parent.name", read_only=True, default=None)
    product_count = serializers.IntegerField(read_only=True, default=0)
    tax_rate_id = WorkspaceRelatedField(TaxRate, source="tax_rate", allow_null=True, required=False)
    tax_rate_name = serializers.CharField(source="tax_rate.name", read_only=True, default=None)
    income_account_id = WorkspaceRelatedField(LedgerAccount, source="income_account", allow_null=True, required=False)
    income_account_name = serializers.CharField(source="income_account.name", read_only=True, default=None)

    class Meta:
        model = ProductCategory
        fields = ["id", "name", "parent_id", "parent_name", "description", "tax_rate_id", "tax_rate_name", "income_account_id",
                  "income_account_name", "markup_percent", "is_active", "product_count", "created_at"]
        read_only_fields = ["id", "parent_name", "tax_rate_name", "income_account_name", "product_count", "created_at"]

    def validate_name(self, value):
        value = value.strip()
        clash = ProductCategory.objects.filter(workspace=self.context["workspace"], name__iexact=value)
        if self.instance:
            clash = clash.exclude(pk=self.instance.pk)
        if clash.exists():
            raise serializers.ValidationError("There is already a category with this name.")
        return value

    def validate(self, attrs):
        tax = attrs.get("tax_rate")
        if tax is not None and tax.kind != "vat":
            raise serializers.ValidationError({"tax_rate_id": ["Choose a VAT rate."]})
        account = attrs.get("income_account")
        if account is not None and account.account_type != "income":
            raise serializers.ValidationError({"income_account_id": ["Choose an income account."]})
        if attrs.get("markup_percent") is not None and attrs["markup_percent"] < 0:
            raise serializers.ValidationError({"markup_percent": ["The markup can't be negative."]})
        parent = attrs.get("parent")
        node = parent
        while node is not None:
            if self.instance and node.pk == self.instance.pk:
                raise serializers.ValidationError({"parent_id": ["A category can't sit inside itself."]})
            node = node.parent
        return attrs
