from rest_framework import serializers

from apps.core.fields import WorkspaceRelatedField
from apps.departments.models import Department
from apps.roles.models import Role

from .models import Membership


class MemberUserSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    email = serializers.EmailField()
    full_name = serializers.CharField()
    avatar_url = serializers.URLField(allow_blank=True)


class MembershipSerializer(serializers.ModelSerializer):
    user = MemberUserSerializer(read_only=True)
    role_id = serializers.PrimaryKeyRelatedField(source="role", queryset=Role.objects.none())
    role_name = serializers.CharField(source="role.name", read_only=True)
    employee_id = serializers.SerializerMethodField()
    limited_department_id = WorkspaceRelatedField(Department, source="limited_department", allow_null=True, required=False,
                                                  help_text="Sees only this department's documents and reports. Null: the whole business.")
    limited_department_name = serializers.CharField(source="limited_department.name", read_only=True, default=None)

    class Meta:
        model = Membership
        fields = ["id", "user", "role_id", "role_name", "status", "approval_limit", "limited_department_id", "limited_department_name", "employee_id",
                  "created_at"]
        read_only_fields = ["id", "user", "role_name", "limited_department_name", "employee_id", "created_at"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        workspace = self.context.get("workspace")
        if workspace is not None:
            self.fields["role_id"].queryset = Role.objects.filter(workspace=workspace)

    def get_employee_id(self, obj) -> str | None:
        employee = getattr(obj, "employee", None)
        return str(employee.id) if employee else None
