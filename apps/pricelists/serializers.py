from rest_framework import serializers

from apps.core.fields import WorkspaceRelatedField
from apps.products.models import Product

from .models import PriceList, PriceListItem


class PriceListItemSerializer(serializers.ModelSerializer):
    product_id = WorkspaceRelatedField(Product, source="product")
    product_name = serializers.CharField(source="product.name", read_only=True)
    normal_price = serializers.DecimalField(source="product.sale_price", max_digits=18, decimal_places=4, read_only=True)

    class Meta:
        model = PriceListItem
        fields = ["id", "product_id", "product_name", "normal_price", "price"]
        read_only_fields = ["id", "product_name", "normal_price"]


class PriceListSerializer(serializers.ModelSerializer):
    items = PriceListItemSerializer(many=True, required=False)
    customer_count = serializers.IntegerField(read_only=True, default=0)

    class Meta:
        model = PriceList
        fields = ["id", "name", "description", "adjust_percent", "is_active", "items", "customer_count", "created_at"]
        read_only_fields = ["id", "customer_count", "created_at"]

    def validate_adjust_percent(self, value):
        if value <= -100:
            raise serializers.ValidationError("The adjustment must be above -100%.")
        return value

    def validate_items(self, items):
        seen = set()
        for item in items:
            if item["product"].pk in seen:
                raise serializers.ValidationError(f"{item['product']} is listed twice.")
            if item["price"] < 0:
                raise serializers.ValidationError("Prices can't be negative.")
            seen.add(item["product"].pk)
        return items

    def _save_items(self, price_list, items):
        if items is None:
            return
        price_list.items.all().delete()
        PriceListItem.objects.bulk_create(PriceListItem(price_list=price_list, product=i["product"], price=i["price"]) for i in items)

    def create(self, validated_data):
        items = validated_data.pop("items", [])
        price_list = super().create(validated_data)
        self._save_items(price_list, items)
        return price_list

    def update(self, instance, validated_data):
        items = validated_data.pop("items", None)
        price_list = super().update(instance, validated_data)
        self._save_items(price_list, items)
        return price_list
