from rest_framework import serializers

from apps.core.catalog import DEPARTMENT_MODULES
from apps.core.codes import AutoCodeMixin
from apps.employees.models import Employee
from apps.memberships.models import Membership

from .models import Department


class DepartmentSerializer(AutoCodeMixin, serializers.ModelSerializer):
    code_key = "department"
    head_id = serializers.PrimaryKeyRelatedField(
        source="head", queryset=Employee.objects.none(), allow_null=True, required=False
    )
    head_name = serializers.CharField(source="head.full_name", read_only=True, default=None)
    head_membership_id = serializers.PrimaryKeyRelatedField(
        queryset=Membership.objects.none(), write_only=True, required=False, allow_null=True,
        help_text="A team member without a staff record: one is made for them and they become the head",
    )
    employee_count = serializers.IntegerField(read_only=True, default=0)

    class Meta:
        model = Department
        fields = [
            "id", "name", "code", "description", "head_id", "head_name", "head_membership_id", "modules", "is_active",
            "employee_count", "created_at",
        ]
        read_only_fields = ["id", "head_name", "employee_count", "created_at"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        workspace = self.context.get("workspace")
        if workspace is not None:
            self.fields["head_id"].queryset = Employee.objects.filter(workspace=workspace)
            self.fields["head_membership_id"].queryset = Membership.objects.filter(workspace=workspace, status="active")

    def validate_name(self, value):
        value = value.strip()
        clash = Department.objects.filter(workspace=self.context["workspace"], name__iexact=value)
        if self.instance:
            clash = clash.exclude(pk=self.instance.pk)
        if clash.exists():
            raise serializers.ValidationError("A department with this name already exists.")
        return value

    def validate_modules(self, value):
        if not isinstance(value, list):
            raise serializers.ValidationError("Send a list of module keys.")
        unknown = [m for m in value if m not in DEPARTMENT_MODULES]
        if unknown:
            raise serializers.ValidationError(f"Unknown modules: {', '.join(unknown)}.")
        # One in-charge per module: a module belongs to one department only.
        taken = Department.objects.filter(workspace=self.context["workspace"], is_active=True)
        if self.instance:
            taken = taken.exclude(pk=self.instance.pk)
        clashes = [f"{DEPARTMENT_MODULES[m]} ({d.name})" for d in taken for m in value if m in d.modules]
        if clashes:
            raise serializers.ValidationError(f"Already run by another department: {', '.join(clashes)}.")
        return sorted(set(value))

    def _head(self, validated):
        member = validated.pop("head_membership_id", None)
        if member is not None:
            from apps.employees.services import employee_for_membership

            validated["head"] = employee_for_membership(member)

    @staticmethod
    def _head_joins(department):
        """The head belongs to the department they run, unless they are already in another one."""
        head = department.head
        if head is not None and head.department_id is None:
            head.department = department
            head.save(update_fields=["department", "updated_at"])

    def create(self, validated_data):
        self._head(validated_data)
        department = super().create(validated_data)
        self._head_joins(department)
        return department

    def update(self, instance, validated_data):
        self._head(validated_data)
        department = super().update(instance, validated_data)
        self._head_joins(department)
        return department
