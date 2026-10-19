from rest_framework import serializers

from apps.core.fields import WorkspaceRelatedField
from apps.customers.models import Customer
from apps.employees.models import Employee

from .models import Project


class ProjectSerializer(serializers.ModelSerializer):
    customer_id = WorkspaceRelatedField(Customer, source="customer", allow_null=True, required=False)
    customer_name = serializers.CharField(source="customer.name", read_only=True, default=None)
    manager_id = WorkspaceRelatedField(Employee, source="manager", allow_null=True, required=False)
    manager_name = serializers.CharField(source="manager.full_name", read_only=True, default=None)

    class Meta:
        model = Project
        fields = ["id", "code", "name", "customer_id", "customer_name", "manager_id", "manager_name", "status", "start_date", "end_date",
                  "contract_value", "cost_budget", "description", "created_at"]
        read_only_fields = ["id", "customer_name", "manager_name", "created_at"]
        extra_kwargs = {"code": {"required": False, "allow_blank": True}}

    def validate_code(self, value):
        value = (value or "").strip().upper()
        if not value:
            return value
        clash = Project.objects.filter(workspace=self.context["workspace"], code__iexact=value)
        if self.instance:
            clash = clash.exclude(pk=self.instance.pk)
        if clash.exists():
            raise serializers.ValidationError("Another project has this code.")
        return value

    def validate(self, attrs):
        start = attrs.get("start_date", getattr(self.instance, "start_date", None))
        end = attrs.get("end_date", getattr(self.instance, "end_date", None))
        if start and end and end < start:
            raise serializers.ValidationError({"end_date": "The end date can't be before the start date."})
        return attrs

    def create(self, validated_data):
        if not validated_data.get("code"):
            from apps.sequences.services import next_value

            validated_data["code"] = next_value(validated_data["workspace"], "project")
        return super().create(validated_data)


class ProjectLineSerializer(serializers.Serializer):
    account_id = serializers.UUIDField()
    code = serializers.CharField()
    name = serializers.CharField()
    kind = serializers.CharField()
    amount = serializers.DecimalField(max_digits=18, decimal_places=2)


class ProjectRecentSerializer(serializers.Serializer):
    date = serializers.DateField()
    entry_id = serializers.UUIDField()
    number = serializers.CharField()
    description = serializers.CharField()
    account = serializers.CharField()
    amount = serializers.DecimalField(max_digits=18, decimal_places=2)
    kind = serializers.CharField()


class ProjectSummarySerializer(serializers.Serializer):
    income = serializers.DecimalField(max_digits=18, decimal_places=2)
    costs = serializers.DecimalField(max_digits=18, decimal_places=2)
    profit = serializers.DecimalField(max_digits=18, decimal_places=2)
    margin_percent = serializers.DecimalField(max_digits=18, decimal_places=2, allow_null=True)
    budget_used_percent = serializers.DecimalField(max_digits=18, decimal_places=2, allow_null=True)
    budget_left = serializers.DecimalField(max_digits=18, decimal_places=2, allow_null=True)
    invoiced = serializers.DecimalField(max_digits=18, decimal_places=2)
    outstanding = serializers.DecimalField(max_digits=18, decimal_places=2)
    contract_left_to_invoice = serializers.DecimalField(max_digits=18, decimal_places=2, allow_null=True)
    by_account = ProjectLineSerializer(many=True)
    recent = ProjectRecentSerializer(many=True)
