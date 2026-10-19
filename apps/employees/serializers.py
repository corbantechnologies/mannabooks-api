from rest_framework import serializers

from apps.branches.models import Branch
from apps.departments.models import Department
from apps.memberships.models import Membership
from apps.roles.models import Role

from .models import Employee


class EmployeeSerializer(serializers.ModelSerializer):
    full_name = serializers.CharField(read_only=True)
    department_id = serializers.PrimaryKeyRelatedField(
        source="department", queryset=Department.objects.none(), allow_null=True, required=False
    )
    department_name = serializers.CharField(source="department.name", read_only=True, default=None)
    branch_id = serializers.PrimaryKeyRelatedField(source="branch", queryset=Branch.objects.none(), allow_null=True, required=False)
    reports_to_id = serializers.PrimaryKeyRelatedField(
        source="reports_to", queryset=Employee.objects.none(), allow_null=True, required=False
    )
    reports_to_name = serializers.CharField(source="reports_to.full_name", read_only=True, default=None)
    membership_id = serializers.PrimaryKeyRelatedField(
        source="membership", queryset=Membership.objects.none(), allow_null=True, required=False
    )
    has_login = serializers.SerializerMethodField()

    class Meta:
        model = Employee
        fields = [
            "id", "staff_number", "first_name", "last_name", "other_names", "full_name", "email", "phone",
            "national_id", "kra_pin", "job_title", "department_id", "department_name", "branch_id",
            "reports_to_id", "reports_to_name", "membership_id", "has_login", "hire_date", "status", "created_at",
            "on_payroll", "basic_salary", "recurring_items", "pay_method", "bank_name", "bank_account_number", "mpesa_phone", "nssf_number", "shif_number", "annual_leave_days", "exit_date",
        ]
        read_only_fields = ["id", "staff_number", "full_name", "department_name", "reports_to_name", "has_login", "created_at"]

    PAY = ("on_payroll", "basic_salary", "recurring_items", "pay_method", "bank_name", "bank_account_number", "mpesa_phone", "nssf_number", "shif_number", "annual_leave_days", "exit_date")

    def to_representation(self, instance):
        """Pay details are shown only to payroll staff and to the employee themself."""
        data = super().to_representation(instance)
        request = self.context.get("request")
        membership = getattr(request, "membership", None) if request else None
        if membership is not None and not membership.has_perm("payroll.view") and instance.membership_id != membership.id:
            for field in self.PAY:
                data.pop(field, None)
        return data

    def validate_recurring_items(self, items):
        if not isinstance(items, list):
            raise serializers.ValidationError("A list of items.")
        clean = []
        for item in items:
            try:
                amount = round(float(item.get("amount", 0)), 2)
            except (TypeError, ValueError, AttributeError):
                raise serializers.ValidationError("Each item needs a name, a kind and an amount.") from None
            if not item.get("name") or item.get("kind") not in ("earning", "deduction") or amount <= 0:
                raise serializers.ValidationError("Each item needs a name, a kind (earning or deduction) and an amount above zero.")
            clean.append({"name": str(item["name"])[:80], "kind": item["kind"], "amount": amount, "taxable": bool(item.get("taxable", True))})
        return clean

    def _strip_pay(self, attrs):
        request = self.context.get("request")
        membership = getattr(request, "membership", None) if request else None
        if membership is not None and not membership.has_perm("payroll.manage"):
            for field in self.PAY:
                attrs.pop(field, None)  # only payroll staff change pay
        return attrs

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        workspace = self.context.get("workspace")
        if workspace is not None:
            self.fields["department_id"].queryset = Department.objects.filter(workspace=workspace)
            self.fields["branch_id"].queryset = Branch.objects.filter(workspace=workspace)
            self.fields["reports_to_id"].queryset = Employee.objects.filter(workspace=workspace)
            self.fields["membership_id"].queryset = Membership.objects.filter(workspace=workspace)

    def get_has_login(self, obj) -> bool:
        return obj.membership_id is not None

    def validate_kra_pin(self, value):
        return value.strip().upper()

    def validate(self, attrs):
        attrs = self._strip_pay(attrs)
        manager = attrs.get("reports_to")
        if manager is not None and self.instance is not None:
            seen, node = set(), manager
            while node is not None:
                if node.pk == self.instance.pk:
                    raise serializers.ValidationError({"reports_to_id": ["This would make a reporting loop."]})
                if node.pk in seen:
                    break
                seen.add(node.pk)
                node = node.reports_to
        membership = attrs.get("membership")
        if membership is not None:
            linked = Employee.objects.filter(membership=membership)
            if self.instance:
                linked = linked.exclude(pk=self.instance.pk)
            if linked.exists():
                raise serializers.ValidationError({"membership_id": ["That login is already linked to another employee."]})
        return attrs


class EmployeeInviteSerializer(serializers.Serializer):
    """Give an employee a login: an invitation to their email, with the Self-service role by default."""

    role_id = serializers.PrimaryKeyRelatedField(queryset=Role.objects.none(), required=False, allow_null=True)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        workspace = self.context.get("workspace")
        if workspace is not None:
            self.fields["role_id"].queryset = Role.objects.filter(workspace=workspace)
