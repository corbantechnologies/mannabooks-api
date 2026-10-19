from rest_framework import serializers

from apps.branches.models import Branch
from apps.core.fields import WorkspaceRelatedField
from apps.ledgeraccounts.models import LedgerAccount

from .models import PosRegister


class PosRegisterSerializer(serializers.ModelSerializer):
    branch_id = WorkspaceRelatedField(Branch, source="branch", allow_null=True, required=False)
    branch_name = serializers.CharField(source="branch.name", read_only=True, default=None)
    cash_account_id = WorkspaceRelatedField(LedgerAccount, source="cash_account", allow_null=True, required=False)
    mpesa_account_id = WorkspaceRelatedField(LedgerAccount, source="mpesa_account", allow_null=True, required=False)
    card_account_id = WorkspaceRelatedField(LedgerAccount, source="card_account", allow_null=True, required=False)
    open_shift_id = serializers.SerializerMethodField()

    class Meta:
        model = PosRegister
        fields = ["id", "name", "branch_id", "branch_name", "cash_account_id", "mpesa_account_id", "card_account_id",
                  "receipt_footer", "is_active", "open_shift_id", "created_at"]
        read_only_fields = ["id", "branch_name", "open_shift_id", "created_at"]

    def get_open_shift_id(self, obj) -> str | None:
        shift = obj.shifts.filter(status="open").first()
        return str(shift.id) if shift else None

    def validate(self, attrs):
        for field in ("cash_account", "mpesa_account", "card_account"):
            account = attrs.get(field)
            if account is not None and account.subtype not in ("cash", "bank"):
                raise serializers.ValidationError({f"{field}_id": ["Choose a cash, bank or M-Pesa account."]})
        return attrs
