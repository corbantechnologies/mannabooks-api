from django.db import transaction
from django.utils import timezone
from rest_framework import serializers

from apps.core.codes import AutoCodeMixin
from apps.core.fields import WorkspaceRelatedField
from apps.ledgeraccounts.models import LedgerAccount
from apps.productcategories.models import ProductCategory
from apps.taxrates.models import TaxRate
from apps.warehouses.models import Warehouse

from .models import Product


class ProductSerializer(AutoCodeMixin, serializers.ModelSerializer):
    code_key = "product"
    tax_rate_id = WorkspaceRelatedField(TaxRate, source="tax_rate", allow_null=True, required=False)
    tax_rate_name = serializers.CharField(source="tax_rate.name", read_only=True, default=None)
    income_account_id = WorkspaceRelatedField(LedgerAccount, source="income_account", allow_null=True, required=False)
    category_id = WorkspaceRelatedField(ProductCategory, source="category", allow_null=True, required=False)
    category_name = serializers.CharField(source="category.name", read_only=True, default=None)
    stock_on_hand = serializers.DecimalField(max_digits=14, decimal_places=3, read_only=True, default=None,
                                             help_text="All warehouses; blank if stock isn't tracked")
    opening_quantity = serializers.DecimalField(max_digits=14, decimal_places=3, min_value=0, write_only=True, required=False,
                                                help_text="Stock already on the shelf, for a tracked product with no stock yet")
    opening_unit_cost = serializers.DecimalField(max_digits=18, decimal_places=4, min_value=0, write_only=True, required=False,
                                                 help_text="What each unit cost; blank: the cost price")
    opening_warehouse_id = WorkspaceRelatedField(Warehouse, source="opening_warehouse", write_only=True, required=False, allow_null=True,
                                                 help_text="Blank: the default warehouse")

    class Meta:
        model = Product
        fields = [
            "id", "code", "name", "kind", "category_id", "category_name", "description", "unit", "sale_price", "cost_price", "tax_rate_id",
            "tax_rate_name", "income_account_id", "track_inventory", "reorder_level", "stock_on_hand", "is_active", "created_at",
            "opening_quantity", "opening_unit_cost", "opening_warehouse_id",
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

    OPENING = ("opening_quantity", "opening_unit_cost", "opening_warehouse")

    def _opening(self, product, opening: dict) -> None:
        """Stock already on hand, recorded as an opening stock adjustment (against opening balance equity)."""
        quantity = opening.get("opening_quantity")
        if not quantity:
            return
        from apps.core.exceptions import BusinessRuleError
        from apps.stockadjustments import services as adjustments
        from apps.stockmovements.models import StockMovement
        from apps.warehouses.services import default_warehouse

        if not product.track_inventory:
            raise BusinessRuleError("Tick \"Track stock\" to record the quantity on hand.")
        if StockMovement.objects.filter(product=product).exists():
            raise BusinessRuleError("This product already has stock records. Change its stock in Inventory > Adjustments.")
        cost = opening.get("opening_unit_cost") or product.cost_price
        if not cost:
            raise BusinessRuleError("Enter what each unit cost you, so the stock can be valued.")
        request = self.context.get("request")
        adjustments.create(product.workspace, warehouse=opening.get("opening_warehouse") or default_warehouse(product.workspace),
                           adjustment_date=timezone.localdate(), reason="opening", notes=f"Opening stock entered with {product}",
                           rows=[{"product": product, "quantity": quantity, "unit_cost": cost}], user=getattr(request, "user", None))

    @transaction.atomic
    def create(self, validated_data):
        opening = {k: validated_data.pop(k) for k in self.OPENING if k in validated_data}
        product = super().create(validated_data)
        self._opening(product, opening)
        return product

    @transaction.atomic
    def update(self, instance, validated_data):
        opening = {k: validated_data.pop(k) for k in self.OPENING if k in validated_data}
        product = super().update(instance, validated_data)
        self._opening(product, opening)
        return product
