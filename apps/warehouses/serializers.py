from rest_framework import serializers

from apps.branches.models import Branch
from apps.core.fields import WorkspaceRelatedField

from .models import Warehouse


class WarehouseSerializer(serializers.ModelSerializer):
    branch_id = WorkspaceRelatedField(Branch, source="branch", allow_null=True, required=False)
    branch_name = serializers.CharField(source="branch.name", read_only=True, default=None)
    stock_value = serializers.DecimalField(max_digits=18, decimal_places=2, read_only=True, default=0)

    class Meta:
        model = Warehouse
        fields = ["id", "name", "code", "branch_id", "branch_name", "address", "is_default", "is_active", "stock_value", "created_at"]
        read_only_fields = ["id", "branch_name", "stock_value", "created_at"]
