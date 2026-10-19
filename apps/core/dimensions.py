"""The cost centre and project a document is tagged with (shared serializer fields)."""
from rest_framework import serializers

from apps.core.fields import WorkspaceRelatedField
from apps.costcenters.models import CostCenter
from apps.projects.models import Project

DIMENSION_FIELDS = ["cost_center_id", "cost_center_name", "project_id", "project_name"]
DIMENSION_KEYS = ("cost_center", "project")


class DimensionFields(serializers.Serializer):
    cost_center_id = WorkspaceRelatedField(CostCenter, source="cost_center", allow_null=True, required=False)
    cost_center_name = serializers.CharField(source="cost_center.name", read_only=True, default=None)
    project_id = WorkspaceRelatedField(Project, source="project", allow_null=True, required=False)
    project_name = serializers.CharField(source="project.name", read_only=True, default=None)

    def validate_cost_center_id(self, value):
        if value is not None and not value.is_active:
            raise serializers.ValidationError(f"{value} is inactive.")
        return value

    def validate_project_id(self, value):
        if value is not None and value.status == Project.Status.CANCELLED:
            raise serializers.ValidationError(f"{value} is cancelled.")
        return value
