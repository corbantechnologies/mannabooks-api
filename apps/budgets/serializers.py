from rest_framework import serializers

from apps.core.fields import WorkspaceRelatedField
from apps.costcenters.models import CostCenter
from apps.fiscalyears.models import FiscalYear
from apps.ledgeraccounts.models import LedgerAccount
from apps.projects.models import Project

from . import services
from .models import Budget


class BudgetLineSerializer(serializers.Serializer):
    id = serializers.UUIDField(read_only=True)
    account_id = WorkspaceRelatedField(LedgerAccount, source="account")
    account_code = serializers.CharField(source="account.code", read_only=True)
    account_name = serializers.CharField(source="account.name", read_only=True)
    account_type = serializers.CharField(source="account.account_type", read_only=True)
    amounts = serializers.ListField(child=serializers.DecimalField(max_digits=18, decimal_places=2, min_value=0), min_length=12, max_length=12)
    total = serializers.DecimalField(max_digits=18, decimal_places=2, read_only=True)


class BudgetSerializer(serializers.ModelSerializer):
    fiscal_year_id = WorkspaceRelatedField(FiscalYear, source="fiscal_year")
    fiscal_year_name = serializers.CharField(source="fiscal_year.name", read_only=True)
    cost_center_id = WorkspaceRelatedField(CostCenter, source="cost_center", allow_null=True, required=False)
    cost_center_name = serializers.CharField(source="cost_center.name", read_only=True, default=None)
    project_id = WorkspaceRelatedField(Project, source="project", allow_null=True, required=False)
    project_name = serializers.CharField(source="project.name", read_only=True, default=None)
    approved_by_name = serializers.CharField(source="approved_by.full_name", read_only=True, default=None)
    lines = BudgetLineSerializer(many=True, required=False)
    total_income = serializers.SerializerMethodField()
    total_expense = serializers.SerializerMethodField()
    months = serializers.SerializerMethodField()

    class Meta:
        model = Budget
        fields = ["id", "name", "fiscal_year_id", "fiscal_year_name", "cost_center_id", "cost_center_name", "project_id", "project_name", "status",
                  "notes", "approved_by_name", "approved_at", "total_income", "total_expense", "months", "lines", "created_at"]
        read_only_fields = ["id", "fiscal_year_name", "cost_center_name", "project_name", "status", "approved_by_name", "approved_at", "created_at"]

    def _total(self, obj, kind) -> str:
        return str(sum((line.total for line in obj.lines.all() if line.account.account_type == kind), 0))

    def get_total_income(self, obj) -> str:
        return self._total(obj, "income")

    def get_total_expense(self, obj) -> str:
        return self._total(obj, "expense")

    def get_months(self, obj) -> list[str]:
        return [m.isoformat() for m in services.month_starts(obj.fiscal_year)]

    def create(self, validated_data):
        lines = validated_data.pop("lines", [])
        workspace, user = validated_data.pop("workspace"), validated_data.pop("created_by", None)
        return services.save(workspace, header=validated_data, lines=lines, user=user)

    def update(self, instance, validated_data):
        lines = validated_data.pop("lines", None)
        return services.save(instance.workspace, header=validated_data, lines=lines, budget=instance)


class BudgetActionSerializer(serializers.Serializer):
    action = serializers.ChoiceField(choices=["approve", "reopen", "fill_from_last_year"])
    uplift_percent = serializers.DecimalField(max_digits=6, decimal_places=2, required=False, default=0)


class BudgetRowSerializer(serializers.Serializer):
    account_id = serializers.UUIDField()
    code = serializers.CharField()
    name = serializers.CharField()
    kind = serializers.CharField()
    budget = serializers.ListField(child=serializers.DecimalField(max_digits=18, decimal_places=2))
    actual = serializers.ListField(child=serializers.DecimalField(max_digits=18, decimal_places=2))
    budget_total = serializers.DecimalField(max_digits=18, decimal_places=2)
    actual_total = serializers.DecimalField(max_digits=18, decimal_places=2)
    ytd_budget = serializers.DecimalField(max_digits=18, decimal_places=2)
    ytd_actual = serializers.DecimalField(max_digits=18, decimal_places=2)
    variance = serializers.DecimalField(max_digits=18, decimal_places=2)
    favourable = serializers.BooleanField()
    used_percent = serializers.DecimalField(max_digits=18, decimal_places=2, allow_null=True)


class BudgetTotalsSerializer(serializers.Serializer):
    budget = serializers.DecimalField(max_digits=18, decimal_places=2)
    actual = serializers.DecimalField(max_digits=18, decimal_places=2)
    ytd_budget = serializers.DecimalField(max_digits=18, decimal_places=2)
    ytd_actual = serializers.DecimalField(max_digits=18, decimal_places=2)


class BudgetVersusActualSerializer(serializers.Serializer):
    months = serializers.ListField(child=serializers.DateField())
    ytd_months = serializers.IntegerField()
    rows = BudgetRowSerializer(many=True)
    income = BudgetTotalsSerializer()
    expense = BudgetTotalsSerializer()


class BudgetCheckSerializer(serializers.Serializer):
    budgeted = serializers.BooleanField()
    budget_id = serializers.UUIDField(allow_null=True)
    budget_name = serializers.CharField(allow_null=True)
    month_budget = serializers.DecimalField(max_digits=18, decimal_places=2, allow_null=True)
    month_actual = serializers.DecimalField(max_digits=18, decimal_places=2, allow_null=True)
    year_budget = serializers.DecimalField(max_digits=18, decimal_places=2, allow_null=True)
    year_actual = serializers.DecimalField(max_digits=18, decimal_places=2, allow_null=True)
    remaining = serializers.DecimalField(max_digits=18, decimal_places=2, allow_null=True)
    would_exceed = serializers.BooleanField()
