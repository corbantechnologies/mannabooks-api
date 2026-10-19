from rest_framework import serializers

from apps.bankaccounts.models import BankAccount
from apps.core.fields import WorkspaceRelatedField

from .models import Reconciliation
from .services import summary


class ReconciliationSerializer(serializers.ModelSerializer):
    bank_account_id = WorkspaceRelatedField(BankAccount, source="bank_account")
    bank_account_name = serializers.CharField(source="bank_account.name", read_only=True)
    completed_by_name = serializers.CharField(source="completed_by.full_name", read_only=True, default=None)
    cleared_balance = serializers.SerializerMethodField()
    difference = serializers.SerializerMethodField()

    class Meta:
        model = Reconciliation
        fields = ["id", "bank_account_id", "bank_account_name", "statement_date", "statement_balance", "opening_balance", "cleared_balance",
                  "difference", "status", "completed_at", "completed_by_name", "created_at"]
        read_only_fields = ["id", "bank_account_name", "opening_balance", "cleared_balance", "difference", "status", "completed_at",
                            "completed_by_name", "created_at"]

    def get_cleared_balance(self, obj) -> str:
        return str(summary(obj)["cleared_balance"])

    def get_difference(self, obj) -> str:
        return str(summary(obj)["difference"])


class CandidateSerializer(serializers.Serializer):
    journal_line_id = serializers.UUIDField(source="id")
    date = serializers.DateField(source="entry.entry_date")
    description = serializers.CharField(source="entry.description")
    reference = serializers.CharField(source="entry.reference")
    money_in = serializers.DecimalField(source="debit", max_digits=18, decimal_places=2)
    money_out = serializers.DecimalField(source="credit", max_digits=18, decimal_places=2)
    cleared = serializers.BooleanField()


class TickSerializer(serializers.Serializer):
    journal_line_ids = serializers.ListField(child=serializers.UUIDField())
    cleared = serializers.BooleanField()


class ReconciliationActionSerializer(serializers.Serializer):
    action = serializers.ChoiceField(choices=["complete", "reopen"])
