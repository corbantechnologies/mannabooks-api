from rest_framework import serializers

from apps.core.fields import WorkspaceRelatedField
from apps.products.models import Product
from apps.warehouses.models import Warehouse

from .models import StockAdjustment


class AdjustmentLineSerializer(serializers.Serializer):
    id = serializers.UUIDField(read_only=True)
    product_id = WorkspaceRelatedField(Product, source="product")
    product_name = serializers.CharField(source="product.name", read_only=True)
    unit = serializers.CharField(source="product.unit", read_only=True)
    quantity = serializers.DecimalField(max_digits=14, decimal_places=3)
    unit_cost = serializers.DecimalField(max_digits=18, decimal_places=4, required=False, allow_null=True,
                                         help_text="For stock added; blank uses the average cost")
    value = serializers.DecimalField(max_digits=18, decimal_places=2, read_only=True)


class StockAdjustmentSerializer(serializers.ModelSerializer):
    warehouse_id = WorkspaceRelatedField(Warehouse, source="warehouse")
    warehouse_name = serializers.CharField(source="warehouse.name", read_only=True)
    reason_label = serializers.CharField(source="get_reason_display", read_only=True)
    lines = AdjustmentLineSerializer(many=True)

    class Meta:
        model = StockAdjustment
        fields = ["id", "number", "warehouse_id", "warehouse_name", "adjustment_date", "reason", "reason_label", "status", "total_value", "notes",
                  "lines", "created_at"]
        read_only_fields = ["id", "number", "warehouse_name", "reason_label", "status", "total_value", "created_at"]
        extra_kwargs = {"adjustment_date": {"required": False}}
