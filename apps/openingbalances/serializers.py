from rest_framework import serializers

from apps.core.fields import WorkspaceRelatedField
from apps.ledgeraccounts.models import LedgerAccount

from .models import OpeningBalance, OpeningBalanceLine


class OpeningBalanceLineSerializer(serializers.ModelSerializer):
    account_id = WorkspaceRelatedField(LedgerAccount, source="account")
    account_code = serializers.CharField(source="account.code", read_only=True)
    account_name = serializers.CharField(source="account.name", read_only=True)

    class Meta:
        model = OpeningBalanceLine
        fields = ["account_id", "account_code", "account_name", "debit", "credit"]


class OpeningBalanceSerializer(serializers.ModelSerializer):
    lines = OpeningBalanceLineSerializer(many=True)
    journal_number = serializers.CharField(source="journal.number", read_only=True, default=None)
    total_debit = serializers.SerializerMethodField()
    total_credit = serializers.SerializerMethodField()

    class Meta:
        model = OpeningBalance
        fields = ["id", "as_of_date", "status", "notes", "lines", "total_debit", "total_credit", "journal_number"]
        read_only_fields = ["id", "status", "total_debit", "total_credit", "journal_number"]

    def get_total_debit(self, obj) -> str:
        return str(sum((line.debit for line in obj.lines.all()), 0))

    def get_total_credit(self, obj) -> str:
        return str(sum((line.credit for line in obj.lines.all()), 0))
