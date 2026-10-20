from decimal import Decimal

from django.db import transaction
from django.utils import timezone
from rest_framework import serializers

from apps.core.codes import AutoCodeMixin
from apps.core.fields import WorkspaceRelatedField
from apps.ledgeraccounts.models import LedgerAccount
from apps.productcategories.models import ProductCategory
from apps.taxrates.models import TaxRate
from apps.warehouses.models import Warehouse

from .models import Product, ProductUnit


class ProductUnitSerializer(serializers.Serializer):
    id = serializers.UUIDField(read_only=True)
    unit = serializers.CharField(max_length=20)
    factor = serializers.DecimalField(max_digits=14, decimal_places=4, help_text="How many of the product's own unit one of these holds")
    sale_price = serializers.DecimalField(max_digits=18, decimal_places=4, allow_null=True, required=False,
                                          help_text="Blank: the product's price times the factor")


class ProductSerializer(AutoCodeMixin, serializers.ModelSerializer):
    code_key = "product"
    tax_rate_id = WorkspaceRelatedField(TaxRate, source="tax_rate", allow_null=True, required=False)
    tax_rate_name = serializers.CharField(source="tax_rate.name", read_only=True, default=None)
    income_account_id = WorkspaceRelatedField(LedgerAccount, source="income_account", allow_null=True, required=False)
    category_id = WorkspaceRelatedField(ProductCategory, source="category", allow_null=True, required=False)
    category_name = serializers.CharField(source="category.name", read_only=True, default=None)
    stock_on_hand = serializers.DecimalField(max_digits=14, decimal_places=3, read_only=True, default=None,
                                             help_text="All warehouses; blank if stock isn't tracked")
    units = ProductUnitSerializer(many=True, required=False, help_text="Other units it is bought or sold in, e.g. a carton of 24")
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
            "tax_rate_name", "income_account_id", "track_inventory", "made_to_order", "online", "image_url", "reorder_level", "stock_on_hand", "units", "is_active", "created_at",
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
        made = attrs.get("made_to_order", getattr(self.instance, "made_to_order", False))
        if made and kind != "goods":
            raise serializers.ValidationError({"made_to_order": ["Only goods are made from a recipe."]})
        if made and attrs.get("track_inventory", getattr(self.instance, "track_inventory", False)):
            raise serializers.ValidationError({"made_to_order": ["A made-to-order product has no stock of its own: its ingredients are taken out when it is sold. Untick Track stock."]})
        if self.instance and self.instance.track_inventory and attrs.get("track_inventory") is False:
            from apps.stockmovements.models import StockLevel

            if StockLevel.objects.filter(product=self.instance).exclude(quantity=0).exists():
                raise serializers.ValidationError({"track_inventory": ["This product has stock. Adjust it to zero first."]})
        for field in ("sale_price", "cost_price"):
            if attrs.get(field) is not None and attrs[field] < 0:
                raise serializers.ValidationError({field: ["Prices can't be negative."]})
        base = attrs.get("unit", getattr(self.instance, "unit", "pcs"))
        seen = set()
        for row in attrs.get("units") or []:
            row["unit"] = row["unit"].strip()
            if row["unit"] == base:
                raise serializers.ValidationError({"units": [f"{base} is the product's own unit; add a different one."]})
            if row["unit"] in seen:
                raise serializers.ValidationError({"units": [f"{row['unit']} is listed twice."]})
            if row["factor"] <= 0 or (row.get("sale_price") is not None and row["sale_price"] < 0):
                raise serializers.ValidationError({"units": [f"{row['unit']}: the quantity must be more than zero and the price not negative."]})
            seen.add(row["unit"])
        if self.instance is None:
            self._category_defaults(attrs)
        return attrs

    def _category_defaults(self, attrs):
        """A new product in a category takes the category's VAT rate, income account and markup unless they are given."""
        category = attrs.get("category")
        if category is None:
            return
        given = self.initial_data
        # left out or blank ("workspace default") both mean: use the category's
        if not given.get("tax_rate_id") and category.setting("tax_rate") is not None:
            attrs["tax_rate"] = category.setting("tax_rate")
        if not given.get("income_account_id") and category.setting("income_account") is not None:
            attrs["income_account"] = category.setting("income_account")
        markup = category.setting("markup_percent")
        if markup is not None and not attrs.get("sale_price") and attrs.get("cost_price"):
            attrs["sale_price"] = (attrs["cost_price"] * (1 + markup / 100)).quantize(Decimal("0.01"))

    def _save_units(self, product, rows):
        if rows is None:
            return
        product.units.all().delete()
        getattr(product, "_prefetched_objects_cache", {}).pop("units", None)
        ProductUnit.objects.bulk_create(ProductUnit(product=product, unit=row["unit"], factor=row["factor"], sale_price=row.get("sale_price"))
                                        for row in rows)

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
        units = validated_data.pop("units", None)
        product = super().create(validated_data)
        self._save_units(product, units)
        self._opening(product, opening)
        return product

    @transaction.atomic
    def update(self, instance, validated_data):
        opening = {k: validated_data.pop(k) for k in self.OPENING if k in validated_data}
        units = validated_data.pop("units", None)
        product = super().update(instance, validated_data)
        self._save_units(product, units)
        self._opening(product, opening)
        return product
