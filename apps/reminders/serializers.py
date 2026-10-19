from rest_framework import serializers

from apps.core.fields import WorkspaceRelatedField
from apps.invoices.models import Invoice

from .models import ReminderLog, ReminderRule


class ReminderRuleSerializer(serializers.ModelSerializer):
    class Meta:
        model = ReminderRule
        fields = ["id", "name", "days", "subject", "message", "is_active", "created_at"]
        read_only_fields = ["id", "created_at"]

    def validate_days(self, value):
        if not -60 <= value <= 365:
            raise serializers.ValidationError("Use between 60 days before and 365 days after the due date.")
        return value


class ReminderLogSerializer(serializers.ModelSerializer):
    invoice_id = serializers.UUIDField(source="invoice.id", read_only=True)
    invoice_number = serializers.CharField(source="invoice.number", read_only=True)
    customer_name = serializers.CharField(source="invoice.customer.name", read_only=True)
    rule_name = serializers.CharField(source="rule.name", read_only=True, default=None)

    class Meta:
        model = ReminderLog
        fields = ["id", "invoice_id", "invoice_number", "customer_name", "rule_name", "sent_to", "subject", "error", "created_at"]


class SendReminderSerializer(serializers.Serializer):
    invoice_id = WorkspaceRelatedField(Invoice, source="invoice")
