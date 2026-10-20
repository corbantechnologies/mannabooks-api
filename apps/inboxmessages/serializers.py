from rest_framework import serializers

from apps.core.fields import WorkspaceRelatedField
from apps.ledgeraccounts.models import LedgerAccount

from .models import InboxMessage


class InboxLineSerializer(serializers.Serializer):
    description = serializers.CharField()
    quantity = serializers.CharField()
    unit = serializers.CharField(allow_blank=True)
    unit_price = serializers.CharField()
    tax_code = serializers.CharField(allow_blank=True)
    net = serializers.CharField()
    tax = serializers.CharField()
    total = serializers.CharField()


class InboxMessageSerializer(serializers.ModelSerializer):
    lines = InboxLineSerializer(many=True, read_only=True)
    recipient_name = serializers.CharField(source="workspace.name", read_only=True)
    sent_by_name = serializers.CharField(source="sent_by.full_name", read_only=True, default=None)

    class Meta:
        model = InboxMessage
        fields = ["id", "kind", "status", "sender_name", "sender_kra_pin", "recipient_name", "sent_by_name", "number", "document_date", "due_date",
                  "currency", "prices_include_tax", "subtotal", "tax_total", "total", "lines", "message", "read_at", "decided_at",
                  "decline_reason", "created_type", "created_id", "source_id", "created_at"]
        read_only_fields = fields


class InboxSendSerializer(serializers.Serializer):
    kind = serializers.ChoiceField(choices=InboxMessage.Kind.choices)
    document_id = serializers.UUIDField()
    message = serializers.CharField(required=False, allow_blank=True, max_length=2000)


class PreviewSerializer(serializers.Serializer):
    available = serializers.BooleanField(help_text="The customer or supplier's business is on MannaBooks")
    recipient_name = serializers.CharField(allow_blank=True)
    kra_pin = serializers.CharField(allow_blank=True)
    last_status = serializers.CharField(allow_null=True)
    last_sent_at = serializers.DateTimeField(allow_null=True)


class AcceptSerializer(serializers.Serializer):
    account_id = WorkspaceRelatedField(LedgerAccount, source="account", required=False, allow_null=True,
                                       help_text="For an invoice: the expense or asset account the bill is recorded in")


class DeclineSerializer(serializers.Serializer):
    reason = serializers.CharField(max_length=255)
