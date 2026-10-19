from rest_framework import serializers

from apps.core.fields import WorkspaceRelatedField
from apps.ledgeraccounts.models import LedgerAccount
from apps.productcategories.models import ProductCategory
from apps.taxrates.models import TaxRate

from .models import Product


class ProductSerializer(serializers.ModelSerializer):
    tax_rate_id = WorkspaceRelatedField(TaxRate, source="tax_rate", allow_null=True, required=False)
    tax_rate_name = serializers.CharField(source="tax_rate.name", read_only=True, default=None)
    income_account_id = WorkspaceRelatedField(LedgerAccount, source="income_account", allow_null=True, required=False)
    category_id = WorkspaceRelatedField(ProductCategory, source="category", allow_null=True, required=False)
    category_name = serializers.CharField(source="category.name", read_only=True, default=None)
    stock_on_hand = serializers.DecimalField(max_digits=14, decimal_places=3, read_only=True, default=None,
                                             help_text="All warehouses; blank if stock isn't tracked")

    class Meta:
        model = Product
        fields = [
            "id", "code", "name", "kind", "category_id", "category_name", "description", "unit", "sale_price", "cost_price", "tax_rate_id",
            "tax_rate_name", "income_account_id", "track_inventory", "reorder_level", "stock_on_hand", "is_active", "created_at",
        ]
        read_only_fields = ["id", "tax_rate_name", "category_name", "stock_on_hand", "created_at"]

    def validate_code(self, value):
        value = value.strip()
        if value:
            clash = Product.objects.filter(workspace=self.context["workspace"], code__iexact=value)
            if self.instance:
                clash = clash.exclude(pk=self.instance.pk)
            if clash.exists():
                raise serializers.ValidationError("Another product uses this code.")
        return value

    def validate(self, attrs):
        tax = attrs.get("tax_rate")
        if tax is not None and tax.kind != "vat":
            raise serializers.ValidationError({"tax_rate_id": ["Choose a VAT rate."]})
        account = attrs.get("income_account")
        if account is not None and account.account_type != "income":
            raise serializers.ValidationError({"income_account_id": ["Choose an income account."]})
        kind = attrs.get("kind", getattr(self.instance, "kind", "goods"))
        if attrs.get("track_inventory") and kind != "goods":
            raise serializers.ValidationError({"track_inventory": ["Only goods have stock."]})
        if self.instance and self.instance.track_inventory and attrs.get("track_inventory") is False:
            from apps.stockmovements.models import StockLevel

            if StockLevel.objects.filter(product=self.instance).exclude(quantity=0).exists():
                raise serializers.ValidationError({"track_inventory": ["This product has stock. Adjust it to zero first."]})
        for field in ("sale_price", "cost_price"):
            if attrs.get(field) is not None and attrs[field] < 0:
                raise serializers.ValidationError({field: ["Prices can't be negative."]})
        return attrs
