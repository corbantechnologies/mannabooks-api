from rest_framework import serializers

from apps.core.dimensions import DimensionFields
from apps.core.fields import WorkspaceRelatedField
from apps.core.purchase_serializers import PURCHASE_FIELDS, PURCHASE_READ_ONLY, PurchaseLineSerializer
from apps.suppliers.models import Supplier

from .models import ServiceOrder


class ServiceOrderSerializer(DimensionFields, serializers.ModelSerializer):
    supplier_id = WorkspaceRelatedField(Supplier, source="supplier")
    supplier_name = serializers.CharField(source="supplier.name", read_only=True)
    approved_by_name = serializers.CharField(source="approved_by.full_name", read_only=True, default=None)
    lines = PurchaseLineSerializer(many=True, required=False)

    class Meta:
        model = ServiceOrder
        fields = PURCHASE_FIELDS + ["order_date", "required_by", "scope", "status", "approved_by_name", "approved_at"]
        read_only_fields = PURCHASE_READ_ONLY + ["status", "approved_by_name", "approved_at"]
        extra_kwargs = {"order_date": {"required": False}}


class ServiceOrderActionSerializer(serializers.Serializer):
    action = serializers.ChoiceField(choices=["approve", "cancel"])
