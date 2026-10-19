from rest_framework import serializers

from apps.core.fields import WorkspaceRelatedField
from apps.employees.models import Employee

from .models import LeaveRequest


class LeaveRequestSerializer(serializers.ModelSerializer):
    employee_id = WorkspaceRelatedField(Employee, source="employee", required=False, help_text="Blank: yourself")
    employee_name = serializers.CharField(source="employee.full_name", read_only=True)
    leave_type_label = serializers.CharField(source="get_leave_type_display", read_only=True)
    decided_by_name = serializers.CharField(source="decided_by.full_name", read_only=True, default=None)
    can_decide = serializers.SerializerMethodField()

    class Meta:
        model = LeaveRequest
        fields = ["id", "employee_id", "employee_name", "leave_type", "leave_type_label", "start_date", "end_date", "days", "reason", "status",
                  "decided_by_name", "decided_at", "decision_note", "can_decide", "created_at"]
        read_only_fields = ["id", "employee_name", "leave_type_label", "days", "status", "decided_by_name", "decided_at", "decision_note",
                            "can_decide", "created_at"]

    def get_can_decide(self, obj) -> bool:
        from .services import can_decide

        request = self.context.get("request")
        membership = getattr(request, "membership", None)
        return bool(membership and obj.status == "pending" and can_decide(membership, obj))


class LeaveDecisionSerializer(serializers.Serializer):
    action = serializers.ChoiceField(choices=["approve", "decline", "cancel"])
    note = serializers.CharField(max_length=255, required=False, allow_blank=True)


class LeaveBalanceSerializer(serializers.Serializer):
    employee_id = serializers.UUIDField()
    employee_name = serializers.CharField()
    year = serializers.IntegerField()
    entitlement = serializers.DecimalField(max_digits=5, decimal_places=1)
    taken = serializers.DecimalField(max_digits=5, decimal_places=1)
    pending = serializers.DecimalField(max_digits=5, decimal_places=1)
    remaining = serializers.DecimalField(max_digits=5, decimal_places=1)
