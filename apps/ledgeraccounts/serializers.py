from rest_framework import serializers

from .models import LedgerAccount


class LedgerAccountSerializer(serializers.ModelSerializer):
    parent_id = serializers.PrimaryKeyRelatedField(source="parent", queryset=LedgerAccount.objects.none(), allow_null=True, required=False)
    is_system = serializers.BooleanField(read_only=True)
    debit_total = serializers.DecimalField(max_digits=18, decimal_places=2, read_only=True, default=0)
    credit_total = serializers.DecimalField(max_digits=18, decimal_places=2, read_only=True, default=0)
    balance = serializers.SerializerMethodField(help_text="On the account's normal side: positive is normal.")

    class Meta:
        model = LedgerAccount
        fields = [
            "id", "code", "name", "account_type", "subtype", "parent_id", "description", "system_key", "is_system",
            "is_active", "debit_total", "credit_total", "balance",
        ]
        read_only_fields = ["id", "system_key", "is_system", "debit_total", "credit_total", "balance"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        workspace = self.context.get("workspace")
        if workspace is not None:
            self.fields["parent_id"].queryset = LedgerAccount.objects.filter(workspace=workspace)

    def get_balance(self, obj) -> str:
        debit, credit = getattr(obj, "debit_total", 0) or 0, getattr(obj, "credit_total", 0) or 0
        return str(debit - credit if obj.is_debit_normal else credit - debit)

    def validate_code(self, value):
        value = value.strip()
        clash = LedgerAccount.objects.filter(workspace=self.context["workspace"], code=value)
        if self.instance:
            clash = clash.exclude(pk=self.instance.pk)
        if clash.exists():
            raise serializers.ValidationError("Another account uses this code.")
        return value

    def validate(self, attrs):
        account_type = attrs.get("account_type", getattr(self.instance, "account_type", None))
        subtype = attrs.get("subtype", getattr(self.instance, "subtype", None))
        allowed = SUBTYPES_BY_TYPE.get(account_type, [])
        if subtype not in allowed:
            raise serializers.ValidationError({"subtype": [f"A {account_type} account can't have the subtype {subtype}."]})
        if self.instance and self.instance.is_system:
            if account_type != self.instance.account_type or subtype != self.instance.subtype:
                raise serializers.ValidationError({"account_type": ["MannaBooks posts to this account automatically; its type can't change."]})
            if attrs.get("is_active") is False:
                raise serializers.ValidationError({"is_active": ["MannaBooks posts to this account automatically; it can't be deactivated."]})
        parent = attrs.get("parent")
        if parent is not None:
            if parent.account_type != account_type:
                raise serializers.ValidationError({"parent_id": ["The parent must be an account of the same type."]})
            if self.instance and (parent.pk == self.instance.pk):
                raise serializers.ValidationError({"parent_id": ["An account can't be its own parent."]})
        return attrs


S = LedgerAccount.Subtype
SUBTYPES_BY_TYPE = {
    "asset": [S.CASH, S.BANK, S.RECEIVABLE, S.INVENTORY, S.CURRENT_ASSET, S.FIXED_ASSET, S.TAX_ASSET],
    "liability": [S.PAYABLE, S.TAX_LIABILITY, S.CURRENT_LIABILITY, S.LONG_TERM_LIABILITY],
    "equity": [S.EQUITY],
    "income": [S.INCOME, S.OTHER_INCOME],
    "expense": [S.COST_OF_SALES, S.EXPENSE, S.OTHER_EXPENSE],
}


class LedgerLineSerializer(serializers.Serializer):
    """One posted line in an account's ledger, with the running balance."""

    entry_id = serializers.UUIDField()
    number = serializers.CharField()
    entry_date = serializers.DateField()
    description = serializers.CharField()
    reference = serializers.CharField(allow_blank=True)
    source = serializers.CharField()
    debit = serializers.DecimalField(max_digits=18, decimal_places=2)
    credit = serializers.DecimalField(max_digits=18, decimal_places=2)
    balance = serializers.DecimalField(max_digits=18, decimal_places=2)


class AccountLedgerSerializer(serializers.Serializer):
    account = LedgerAccountSerializer()
    from_date = serializers.DateField(allow_null=True)
    to_date = serializers.DateField(allow_null=True)
    opening_balance = serializers.DecimalField(max_digits=18, decimal_places=2)
    closing_balance = serializers.DecimalField(max_digits=18, decimal_places=2)
    lines = LedgerLineSerializer(many=True)
