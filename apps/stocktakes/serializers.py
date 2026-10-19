from rest_framework import serializers

from apps.core.fields import WorkspaceRelatedField
from apps.productcategories.models import ProductCategory
from apps.products.models import Product
from apps.warehouses.models import Warehouse

from .models import StockTake


class CountLineSerializer(serializers.Serializer):
    id = serializers.UUIDField(read_only=True)
    product_id = WorkspaceRelatedField(Product, source="product")
    product_name = serializers.CharField(source="product.name", read_only=True)
    unit = serializers.CharField(source="product.unit", read_only=True)
    product_code = serializers.CharField(source="product.code", read_only=True)
    system_quantity = serializers.DecimalField(max_digits=14, decimal_places=3, read_only=True)
    counted_quantity = serializers.DecimalField(max_digits=14, decimal_places=3, allow_null=True)
    difference = serializers.DecimalField(max_digits=14, decimal_places=3, read_only=True)
    value = serializers.DecimalField(max_digits=18, decimal_places=2, read_only=True)


class StockTakeSerializer(serializers.ModelSerializer):
    warehouse_id = WorkspaceRelatedField(Warehouse, source="warehouse")
    warehouse_name = serializers.CharField(source="warehouse.name", read_only=True)
    category_id = WorkspaceRelatedField(ProductCategory, source="category", allow_null=True, required=False)
    category_name = serializers.CharField(source="category.name", read_only=True, default=None)
    lines = CountLineSerializer(many=True, read_only=True)
    counted = serializers.SerializerMethodField()

    class Meta:
        model = StockTake
        fields = ["id", "number", "warehouse_id", "warehouse_name", "category_id", "category_name", "count_date", "status", "difference_value",
                  "notes", "counted", "lines", "created_at"]
        read_only_fields = ["id", "number", "warehouse_name", "category_name", "status", "difference_value", "counted", "created_at"]
        extra_kwargs = {"count_date": {"required": False}}

    def get_counted(self, obj) -> str:
        lines = list(obj.lines.all())
        return f"{sum(1 for line in lines if line.counted_quantity is not None)} of {len(lines)}"


class CountsSerializer(serializers.Serializer):
    counts = CountLineSerializer(many=True)


class StockTakeActionSerializer(serializers.Serializer):
    action = serializers.ChoiceField(choices=["post", "cancel"])
