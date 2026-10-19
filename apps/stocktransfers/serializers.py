from rest_framework import serializers

from apps.core.fields import WorkspaceRelatedField
from apps.products.models import Product
from apps.warehouses.models import Warehouse

from .models import StockTransfer


class TransferLineSerializer(serializers.Serializer):
    id = serializers.UUIDField(read_only=True)
    product_id = WorkspaceRelatedField(Product, source="product")
    product_name = serializers.CharField(source="product.name", read_only=True)
    unit = serializers.CharField(source="product.unit", read_only=True)
    quantity = serializers.DecimalField(max_digits=14, decimal_places=3)
    unit_cost = serializers.DecimalField(max_digits=18, decimal_places=4, read_only=True)


class StockTransferSerializer(serializers.ModelSerializer):
    from_warehouse_id = WorkspaceRelatedField(Warehouse, source="from_warehouse")
    from_warehouse_name = serializers.CharField(source="from_warehouse.name", read_only=True)
    to_warehouse_id = WorkspaceRelatedField(Warehouse, source="to_warehouse")
    to_warehouse_name = serializers.CharField(source="to_warehouse.name", read_only=True)
    lines = TransferLineSerializer(many=True)

    class Meta:
        model = StockTransfer
        fields = ["id", "number", "from_warehouse_id", "from_warehouse_name", "to_warehouse_id", "to_warehouse_name", "transfer_date",
                  "status", "total_value", "notes", "lines", "created_at"]
        read_only_fields = ["id", "number", "from_warehouse_name", "to_warehouse_name", "status", "total_value", "created_at"]
        extra_kwargs = {"transfer_date": {"required": False}}
