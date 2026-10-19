from django.utils import timezone
from rest_framework import serializers

from apps.core.dimensions import DimensionFields
from apps.core.fields import WorkspaceRelatedField
from apps.core.purchase_serializers import PURCHASE_FIELDS, PURCHASE_READ_ONLY, PurchaseLineSerializer
from apps.goodsreceipts.models import GoodsReceipt
from apps.purchaseorders.models import PurchaseOrder
from apps.serviceorders.models import ServiceOrder
from apps.suppliers.models import Supplier
from apps.warehouses.models import Warehouse

from .models import Bill


class BillLineSerializer(PurchaseLineSerializer):
    goods_receipt_line_id = serializers.UUIDField(read_only=True, allow_null=True)


class BillSerializer(DimensionFields, serializers.ModelSerializer):
    supplier_id = WorkspaceRelatedField(Supplier, source="supplier", required=False)
    supplier_name = serializers.CharField(source="supplier.name", read_only=True)
    purchase_order_id = WorkspaceRelatedField(PurchaseOrder, source="purchase_order", allow_null=True, required=False)
    purchase_order_number = serializers.CharField(source="purchase_order.number", read_only=True, default=None)
    goods_receipt_id = WorkspaceRelatedField(GoodsReceipt, source="goods_receipt", allow_null=True, required=False)
    goods_receipt_number = serializers.CharField(source="goods_receipt.number", read_only=True, default=None)
    service_order_id = WorkspaceRelatedField(ServiceOrder, source="service_order", allow_null=True, required=False)
    service_order_number = serializers.CharField(source="service_order.number", read_only=True, default=None)
    warehouse_id = WorkspaceRelatedField(Warehouse, source="warehouse", allow_null=True, required=False)
    is_overdue = serializers.SerializerMethodField()
    lines = BillLineSerializer(many=True, required=False, help_text="Leave out to copy them from the goods received, order or service order")

    class Meta:
        model = Bill
        fields = PURCHASE_FIELDS + [
            "supplier_invoice_number", "supplier_etims_number", "bill_date", "due_date", "purchase_order_id", "purchase_order_number",
            "goods_receipt_id", "goods_receipt_number", "service_order_id", "service_order_number", "warehouse_id", "status", "amount_paid",
            "balance_due", "is_overdue", "void_reason",
        ]
        read_only_fields = PURCHASE_READ_ONLY + ["purchase_order_number", "goods_receipt_number", "service_order_number", "status",
                                                 "amount_paid", "balance_due", "is_overdue", "void_reason"]
        extra_kwargs = {"bill_date": {"required": False}, "due_date": {"required": False}, "supplier_invoice_number": {"required": False}}

    def get_is_overdue(self, obj) -> bool:
        return obj.status in ("posted", "partially_paid") and obj.due_date < timezone.localdate()


class BillVoidSerializer(serializers.Serializer):
    reason = serializers.CharField(max_length=255)
