from rest_framework import serializers

from apps.core.fields import WorkspaceRelatedField
from apps.customers.models import Customer
from apps.leads.models import Lead
from apps.memberships.models import Membership
from apps.quotations.models import Quotation

from .models import Deal


class DealSerializer(serializers.ModelSerializer):
    customer_id = WorkspaceRelatedField(Customer, source="customer", allow_null=True, required=False)
    customer_name = serializers.CharField(source="customer.name", read_only=True, default=None)
    lead_id = WorkspaceRelatedField(Lead, source="lead", allow_null=True, required=False)
    lead_name = serializers.CharField(source="lead.name", read_only=True, default=None)
    assigned_to_id = WorkspaceRelatedField(Membership, source="assigned_to", allow_null=True, required=False)
    assigned_to_name = serializers.CharField(source="assigned_to.user.full_name", read_only=True, default=None)
    quotation_id = WorkspaceRelatedField(Quotation, source="quotation", allow_null=True, required=False)
    quotation_number = serializers.CharField(source="quotation.number", read_only=True, default=None)
    quotation_status = serializers.CharField(source="quotation.status", read_only=True, default=None)
    chance = serializers.IntegerField(read_only=True, help_text="The probability used: the deal's own, else its stage's")
    weighted_value = serializers.DecimalField(max_digits=18, decimal_places=2, read_only=True)

    class Meta:
        model = Deal
        fields = ["id", "number", "title", "customer_id", "customer_name", "lead_id", "lead_name", "stage", "value", "probability", "chance",
                  "weighted_value", "expected_close_date", "assigned_to_id", "assigned_to_name", "quotation_id", "quotation_number",
                  "quotation_status", "closed_at", "lost_reason", "notes", "created_at"]
        read_only_fields = ["id", "number", "stage", "chance", "weighted_value", "quotation_number", "quotation_status", "closed_at",
                            "lost_reason", "created_at"]

    def validate(self, attrs):
        if not self.instance and not (attrs.get("customer") or attrs.get("lead")):
            raise serializers.ValidationError({"customer_id": ["Choose the customer or the lead this deal is with."]})
        p = attrs.get("probability")
        if p is not None and p > 100:
            raise serializers.ValidationError({"probability": ["Use a percentage from 0 to 100."]})
        if attrs.get("value") is not None and attrs["value"] < 0:
            raise serializers.ValidationError({"value": ["The value can't be negative."]})
        return attrs


class DealMoveSerializer(serializers.Serializer):
    stage = serializers.ChoiceField(choices=Deal.Stage.choices)
    lost_reason = serializers.CharField(required=False, allow_blank=True)


class StageSerializer(serializers.Serializer):
    stage = serializers.CharField()
    label = serializers.CharField()
    count = serializers.IntegerField()
    value = serializers.DecimalField(max_digits=18, decimal_places=2)
    weighted = serializers.DecimalField(max_digits=18, decimal_places=2)
    probability = serializers.IntegerField()


class PipelineSerializer(serializers.Serializer):
    stages = StageSerializer(many=True)
    open_value = serializers.DecimalField(max_digits=18, decimal_places=2)
    weighted_value = serializers.DecimalField(max_digits=18, decimal_places=2)
    won_this_month = serializers.DecimalField(max_digits=18, decimal_places=2)
    win_rate = serializers.DecimalField(max_digits=5, decimal_places=1, allow_null=True, help_text="Won of closed deals this month, in percent")
