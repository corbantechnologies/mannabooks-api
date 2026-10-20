from rest_framework import serializers

from apps.core.fields import WorkspaceRelatedField
from apps.customers.models import Customer
from apps.memberships.models import Membership

from .models import Lead


class LeadSerializer(serializers.ModelSerializer):
    assigned_to_id = WorkspaceRelatedField(Membership, source="assigned_to", allow_null=True, required=False)
    assigned_to_name = serializers.CharField(source="assigned_to.user.full_name", read_only=True, default=None)
    customer_id = serializers.UUIDField(read_only=True, allow_null=True)
    customer_name = serializers.CharField(source="customer.name", read_only=True, default=None)
    open_tasks = serializers.IntegerField(read_only=True, default=0)

    class Meta:
        model = Lead
        fields = ["id", "number", "name", "company", "phone", "email", "source", "status", "interest", "estimated_value", "assigned_to_id",
                  "assigned_to_name", "customer_id", "customer_name", "lost_reason", "notes", "open_tasks", "created_at"]
        read_only_fields = ["id", "number", "customer_id", "customer_name", "lost_reason", "open_tasks", "created_at"]

    def validate_status(self, value):
        if value in (Lead.Status.CONVERTED, Lead.Status.LOST):
            raise serializers.ValidationError("Use Convert or Mark lost for this.")
        if self.instance and self.instance.status in (Lead.Status.CONVERTED, Lead.Status.LOST) and value != self.instance.status:
            raise serializers.ValidationError("A converted or lost lead keeps its status. Reopen a lost lead first.")
        return value

    def validate(self, attrs):
        if not self.instance and not (attrs.get("phone") or attrs.get("email")):
            raise serializers.ValidationError({"phone": ["Add a phone number or an email, so someone can follow up."]})
        return attrs


class LeadActionSerializer(serializers.Serializer):
    action = serializers.ChoiceField(choices=["convert", "lose", "reopen"])
    customer_id = WorkspaceRelatedField(Customer, source="customer", required=False, allow_null=True,
                                        help_text="Convert to this existing customer; blank: a new customer from the lead")
    deal_title = serializers.CharField(required=False, allow_blank=True, help_text="Also open a deal with this title")
    deal_value = serializers.DecimalField(max_digits=18, decimal_places=2, required=False, allow_null=True)
    reason = serializers.CharField(required=False, allow_blank=True)
