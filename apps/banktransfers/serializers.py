from rest_framework import serializers

from apps.bankaccounts.models import BankAccount
from apps.core.fields import WorkspaceRelatedField

from .models import BankTransfer


class BankTransferSerializer(serializers.ModelSerializer):
    from_account_id = WorkspaceRelatedField(BankAccount, source="from_account")
    from_account_name = serializers.CharField(source="from_account.name", read_only=True)
    to_account_id = WorkspaceRelatedField(BankAccount, source="to_account")
    to_account_name = serializers.CharField(source="to_account.name", read_only=True)

    class Meta:
        model = BankTransfer
        fields = ["id", "number", "transfer_date", "from_account_id", "from_account_name", "to_account_id", "to_account_name", "amount", "fee",
                  "reference", "notes", "status", "created_at"]
        read_only_fields = ["id", "number", "from_account_name", "to_account_name", "status", "created_at"]
        extra_kwargs = {"transfer_date": {"required": False}}
