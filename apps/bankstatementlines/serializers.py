from rest_framework import serializers

from apps.core.fields import WorkspaceRelatedField
from apps.ledgeraccounts.models import LedgerAccount
from apps.taxrates.models import TaxRate

from .models import BankStatementLine


class BankStatementLineSerializer(serializers.ModelSerializer):
    matched_to = serializers.SerializerMethodField()

    class Meta:
        model = BankStatementLine
        fields = ["id", "bank_account", "line_date", "description", "reference", "amount", "status", "matched_to", "import_batch", "created_at"]
        read_only_fields = fields

    def get_matched_to(self, obj) -> dict | None:
        jl = obj.journal_line
        if jl is None:
            return None
        e = jl.entry
        return {"journal_line_id": str(jl.id), "entry_id": str(e.id), "date": e.entry_date, "description": e.description,
                "reference": e.reference, "source": e.source, "source_id": e.source_id}


class ImportRowSerializer(serializers.Serializer):
    line_date = serializers.DateField()
    description = serializers.CharField(max_length=255)
    reference = serializers.CharField(max_length=80, required=False, allow_blank=True)
    amount = serializers.DecimalField(max_digits=18, decimal_places=2)


class ImportSerializer(serializers.Serializer):
    bank_account_id = serializers.UUIDField()
    rows = ImportRowSerializer(many=True)


class SuggestionSerializer(serializers.Serializer):
    journal_line_id = serializers.UUIDField(source="id")
    date = serializers.DateField(source="entry.entry_date")
    description = serializers.CharField(source="entry.description")
    reference = serializers.CharField(source="entry.reference")
    amount = serializers.SerializerMethodField()
    source = serializers.CharField(source="entry.source")

    def get_amount(self, obj) -> str:
        return str(obj.debit - obj.credit)


class LineActionSerializer(serializers.Serializer):
    action = serializers.ChoiceField(choices=["match", "unmatch", "exclude", "include", "record"])
    journal_line_id = serializers.UUIDField(required=False)
    account_id = WorkspaceRelatedField(LedgerAccount, source="account", required=False)
    tax_rate_id = WorkspaceRelatedField(TaxRate, source="tax_rate", required=False, allow_null=True)
    description = serializers.CharField(max_length=255, required=False, allow_blank=True)
