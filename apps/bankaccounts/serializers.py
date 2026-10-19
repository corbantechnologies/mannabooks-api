from rest_framework import serializers

from .models import BankAccount
from .services import balance


class BankAccountSerializer(serializers.ModelSerializer):
    ledger_account_id = serializers.UUIDField(source="ledger_account.id", read_only=True)
    ledger_code = serializers.CharField(source="ledger_account.code", read_only=True)
    balance = serializers.SerializerMethodField(help_text="Per the books")
    unmatched_lines = serializers.IntegerField(read_only=True, default=0, help_text="Statement lines not yet matched")
    last_reconciled = serializers.DateField(read_only=True, default=None)

    class Meta:
        model = BankAccount
        fields = ["id", "name", "kind", "ledger_account_id", "ledger_code", "bank_name", "branch", "account_number", "is_active", "balance",
                  "unmatched_lines", "last_reconciled", "created_at"]
        read_only_fields = ["id", "ledger_account_id", "ledger_code", "balance", "unmatched_lines", "last_reconciled", "created_at"]

    def get_balance(self, obj) -> str:
        return str(balance(obj))
