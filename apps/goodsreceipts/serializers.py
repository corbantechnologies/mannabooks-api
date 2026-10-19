from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from apps.core.fields import WorkspaceRelatedField
from apps.products.models import Product
from apps.purchaseorders.models import PurchaseOrder, PurchaseOrderLine
from apps.suppliers.models import Supplier
from apps.warehouses.models import Warehouse

from .models import GoodsReceipt


@extend_schema_field(OpenApiTypes.UUID)
class _OrderLineField(serializers.PrimaryKeyRelatedField):
    def get_queryset(self):
        return PurchaseOrderLine.objects.filter(purchase_order__workspace=self.context.get("workspace"))


class GoodsReceiptLineSerializer(serializers.Serializer):
    id = serializers.UUIDField(read_only=True)
    order_line_id = _OrderLineField(source="order_line", allow_null=True, required=False)
    product_id = WorkspaceRelatedField(Product, source="product", required=False)
    description = serializers.CharField(read_only=True)
    quantity = serializers.DecimalField(max_digits=14, decimal_places=3)
    unit_cost = serializers.DecimalField(max_digits=18, decimal_places=4, required=False)
    value = serializers.DecimalField(max_digits=18, decimal_places=2, read_only=True)
    stocked = serializers.BooleanField(read_only=True)
    billed_quantity = serializers.DecimalField(max_digits=14, decimal_places=3, read_only=True)


class GoodsReceiptSerializer(serializers.ModelSerializer):
    supplier_id = WorkspaceRelatedField(Supplier, source="supplier", required=False)
    supplier_name = serializers.CharField(source="supplier.name", read_only=True)
    purchase_order_id = WorkspaceRelatedField(PurchaseOrder, source="purchase_order", allow_null=True, required=False)
    purchase_order_number = serializers.CharField(source="purchase_order.number", read_only=True, default=None)
    warehouse_id = WorkspaceRelatedField(Warehouse, source="warehouse", allow_null=True, required=False)
    warehouse_name = serializers.CharField(source="warehouse.name", read_only=True)
    lines = GoodsReceiptLineSerializer(many=True)
    is_billed = serializers.SerializerMethodField()

    class Meta:
        model = GoodsReceipt
        fields = ["id", "number", "supplier_id", "supplier_name", "purchase_order_id", "purchase_order_number", "warehouse_id", "warehouse_name",
                  "receipt_date", "delivery_note_number", "status", "total_value", "notes", "void_reason", "is_billed", "lines", "created_at"]
        read_only_fields = ["id", "number", "supplier_name", "purchase_order_number", "warehouse_name", "status", "total_value", "void_reason",
                            "is_billed", "created_at"]

    def get_is_billed(self, obj) -> bool:
        return all(line.billed_quantity >= line.quantity for line in obj.lines.all())


class GoodsReceiptVoidSerializer(serializers.Serializer):
    reason = serializers.CharField(max_length=255)
