from rest_framework import serializers

from apps.billsofmaterials.models import BillOfMaterials
from apps.core.fields import WorkspaceRelatedField
from apps.products.models import Product
from apps.warehouses.models import Warehouse

from .models import ProductionOrder


class UsageSerializer(serializers.Serializer):
    component_id = WorkspaceRelatedField(Product, source="component")
    component_name = serializers.CharField(source="component.name", read_only=True)
    unit = serializers.CharField(source="component.unit", read_only=True)
    quantity = serializers.DecimalField(max_digits=14, decimal_places=3)
    unit_cost = serializers.DecimalField(max_digits=18, decimal_places=4, read_only=True)
    value = serializers.DecimalField(max_digits=18, decimal_places=2, read_only=True)


class ProductionOrderSerializer(serializers.ModelSerializer):
    bom_id = WorkspaceRelatedField(BillOfMaterials, source="bom")
    product_id = serializers.UUIDField(source="bom.product.id", read_only=True)
    product_name = serializers.CharField(source="bom.product.name", read_only=True)
    warehouse_id = WorkspaceRelatedField(Warehouse, source="warehouse", required=False)
    warehouse_name = serializers.CharField(source="warehouse.name", read_only=True)
    lines = UsageSerializer(many=True, read_only=True)

    class Meta:
        model = ProductionOrder
        fields = ["id", "number", "bom_id", "product_id", "product_name", "quantity", "warehouse_id", "warehouse_name", "production_date",
                  "status", "total_cost", "unit_cost", "notes", "lines", "created_at"]
        read_only_fields = ["id", "number", "product_id", "product_name", "warehouse_name", "status", "total_cost", "unit_cost", "created_at"]
        extra_kwargs = {"production_date": {"required": False}}


class ProductionActionSerializer(serializers.Serializer):
    action = serializers.ChoiceField(choices=["complete", "cancel"])
    usage = UsageSerializer(many=True, required=False, help_text="What was really used, before completing")
