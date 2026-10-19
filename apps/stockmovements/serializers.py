from rest_framework import serializers

from .models import StockLevel, StockMovement


class StockLevelSerializer(serializers.ModelSerializer):
    product_id = serializers.UUIDField(source="product.id", read_only=True)
    product_name = serializers.CharField(source="product.name", read_only=True)
    product_code = serializers.CharField(source="product.code", read_only=True)
    unit = serializers.CharField(source="product.unit", read_only=True)
    reorder_level = serializers.DecimalField(source="product.reorder_level", max_digits=14, decimal_places=3, read_only=True)
    warehouse_id = serializers.UUIDField(source="warehouse.id", read_only=True)
    warehouse_name = serializers.CharField(source="warehouse.name", read_only=True)
    value = serializers.SerializerMethodField()
    is_low = serializers.SerializerMethodField()

    class Meta:
        model = StockLevel
        fields = ["id", "product_id", "product_name", "product_code", "unit", "warehouse_id", "warehouse_name", "quantity", "average_cost",
                  "value", "reorder_level", "is_low"]
        read_only_fields = fields

    def get_value(self, obj) -> str:
        return str(round(obj.quantity * obj.average_cost, 2))

    def get_is_low(self, obj) -> bool:
        return obj.quantity <= obj.product.reorder_level


class StockMovementSerializer(serializers.ModelSerializer):
    product_id = serializers.UUIDField(source="product.id", read_only=True)
    product_name = serializers.CharField(source="product.name", read_only=True)
    warehouse_name = serializers.CharField(source="warehouse.name", read_only=True)
    kind_label = serializers.CharField(source="get_kind_display", read_only=True)

    class Meta:
        model = StockMovement
        fields = ["id", "product_id", "product_name", "warehouse_name", "movement_date", "kind", "kind_label", "quantity", "unit_cost",
                  "value", "balance_quantity", "source_type", "source_id", "source_number", "created_at"]
        read_only_fields = fields
