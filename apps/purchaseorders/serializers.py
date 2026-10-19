from rest_framework import serializers

from apps.core.dimensions import DimensionFields
from apps.core.fields import WorkspaceRelatedField
from apps.core.purchase_serializers import PURCHASE_FIELDS, PURCHASE_READ_ONLY, PurchaseLineSerializer
from apps.suppliers.models import Supplier
from apps.warehouses.models import Warehouse

from .models import PurchaseOrder


class OrderLineSerializer(PurchaseLineSerializer):
    received_quantity = serializers.DecimalField(max_digits=14, decimal_places=3, read_only=True)
    billed_quantity = serializers.DecimalField(max_digits=14, decimal_places=3, read_only=True)


class PurchaseOrderSerializer(DimensionFields, serializers.ModelSerializer):
    supplier_id = WorkspaceRelatedField(Supplier, source="supplier")
    supplier_name = serializers.CharField(source="supplier.name", read_only=True)
    warehouse_id = WorkspaceRelatedField(Warehouse, source="warehouse", allow_null=True, required=False)
    warehouse_name = serializers.CharField(source="warehouse.name", read_only=True, default=None)
    approved_by_name = serializers.CharField(source="approved_by.full_name", read_only=True, default=None)
    lines = OrderLineSerializer(many=True, required=False)

    class Meta:
        model = PurchaseOrder
        fields = PURCHASE_FIELDS + ["order_date", "expected_date", "warehouse_id", "warehouse_name", "status", "approved_by_name", "approved_at"]
        read_only_fields = PURCHASE_READ_ONLY + ["warehouse_name", "status", "approved_by_name", "approved_at"]
        extra_kwargs = {"order_date": {"required": False}}


class OrderActionSerializer(serializers.Serializer):
    action = serializers.ChoiceField(choices=["approve", "cancel", "close"])
