from rest_framework import serializers

from apps.core.fields import WorkspaceRelatedField
from apps.serviceorders.models import ServiceOrder

from .models import ServiceCompletion


class ServiceCompletionSerializer(serializers.ModelSerializer):
    service_order_id = WorkspaceRelatedField(ServiceOrder, source="service_order")
    service_order_number = serializers.CharField(source="service_order.number", read_only=True)
    supplier_name = serializers.CharField(source="service_order.supplier.name", read_only=True)
    confirmed_by_name = serializers.CharField(source="confirmed_by.full_name", read_only=True, default=None)

    class Meta:
        model = ServiceCompletion
        fields = ["id", "number", "service_order_id", "service_order_number", "supplier_name", "completion_date", "confirmed_by_name",
                  "rating", "notes", "created_at"]
        read_only_fields = ["id", "number", "service_order_number", "supplier_name", "confirmed_by_name", "created_at"]

    def validate_rating(self, value):
        if value is not None and not 1 <= value <= 5:
            raise serializers.ValidationError("Rate from 1 to 5.")
        return value

    def validate_service_order_id(self, order):
        if order.status != "approved":
            raise serializers.ValidationError("Only an approved service order can be completed.")
        return order
