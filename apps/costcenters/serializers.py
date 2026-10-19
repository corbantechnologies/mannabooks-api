from rest_framework import serializers

from apps.core.fields import WorkspaceRelatedField
from apps.departments.models import Department

from .models import CostCenter


class CostCenterSerializer(serializers.ModelSerializer):
    department_id = WorkspaceRelatedField(Department, source="department", allow_null=True, required=False)
    department_name = serializers.CharField(source="department.name", read_only=True, default=None)

    class Meta:
        model = CostCenter
        fields = ["id", "code", "name", "department_id", "department_name", "description", "is_active", "created_at"]
        read_only_fields = ["id", "department_name", "created_at"]

    def validate_code(self, value):
        value = value.strip().upper()
        clash = CostCenter.objects.filter(workspace=self.context["workspace"], code__iexact=value)
        if self.instance:
            clash = clash.exclude(pk=self.instance.pk)
        if clash.exists():
            raise serializers.ValidationError("Another cost centre has this code.")
        return value
