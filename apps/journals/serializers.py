from rest_framework import serializers

from apps.branches.models import Branch
from apps.core.fields import WorkspaceRelatedField
from apps.costcenters.models import CostCenter
from apps.departments.models import Department
from apps.ledgeraccounts.models import LedgerAccount
from apps.projects.models import Project

from .models import JournalEntry, JournalLine


class JournalLineSerializer(serializers.ModelSerializer):
    account_id = WorkspaceRelatedField(LedgerAccount, source="account")
    account_code = serializers.CharField(source="account.code", read_only=True)
    account_name = serializers.CharField(source="account.name", read_only=True)
    branch_id = WorkspaceRelatedField(Branch, source="branch", allow_null=True, required=False)
    department_id = WorkspaceRelatedField(Department, source="department", allow_null=True, required=False)
    cost_center_id = WorkspaceRelatedField(CostCenter, source="cost_center", allow_null=True, required=False)
    project_id = WorkspaceRelatedField(Project, source="project", allow_null=True, required=False)

    class Meta:
        model = JournalLine
        fields = ["id", "account_id", "account_code", "account_name", "description", "debit", "credit", "branch_id", "department_id",
                  "cost_center_id", "project_id"]
        read_only_fields = ["id", "account_code", "account_name"]


class JournalEntrySerializer(serializers.ModelSerializer):
    lines = JournalLineSerializer(many=True)
    total = serializers.SerializerMethodField()
    posted_by_name = serializers.CharField(source="posted_by.full_name", read_only=True, default=None)
    reversal_of_number = serializers.CharField(source="reversal_of.number", read_only=True, default=None)
    reversed_by_number = serializers.SerializerMethodField()

    class Meta:
        model = JournalEntry
        fields = [
            "id", "number", "entry_date", "description", "reference", "status", "source", "lines", "total",
            "posted_at", "posted_by_name", "reversal_of_number", "reversed_by_number", "created_at",
        ]
        read_only_fields = ["id", "number", "status", "source", "total", "posted_at", "posted_by_name", "reversal_of_number", "reversed_by_number", "created_at"]

    def get_total(self, obj) -> str:
        return str(sum((line.debit for line in obj.lines.all()), 0))

    def get_reversed_by_number(self, obj) -> str | None:
        reversal = getattr(obj, "reversed_by", None)
        return reversal.number if reversal else None

    def validate_lines(self, value):
        if len(value) < 2:
            raise serializers.ValidationError("Add at least two lines.")
        return value


class JournalListSerializer(serializers.ModelSerializer):
    total = serializers.DecimalField(max_digits=18, decimal_places=2, read_only=True)

    class Meta:
        model = JournalEntry
        fields = ["id", "number", "entry_date", "description", "reference", "status", "source", "total", "created_at"]
        read_only_fields = fields


class ReverseSerializer(serializers.Serializer):
    entry_date = serializers.DateField()
    reason = serializers.CharField(max_length=200, required=False, allow_blank=True)
