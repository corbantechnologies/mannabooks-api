from django.utils import timezone
from rest_framework import serializers

from apps.core.fields import WorkspaceRelatedField
from apps.customers.models import Customer
from apps.deals.models import Deal
from apps.leads.models import Lead
from apps.memberships.models import Membership

from .models import Activity


class ActivitySerializer(serializers.ModelSerializer):
    assigned_to_id = WorkspaceRelatedField(Membership, source="assigned_to", allow_null=True, required=False,
                                           help_text="Blank on a new activity: the person adding it")
    assigned_to_name = serializers.CharField(source="assigned_to.user.full_name", read_only=True, default=None)
    lead_id = WorkspaceRelatedField(Lead, source="lead", allow_null=True, required=False)
    lead_name = serializers.CharField(source="lead.name", read_only=True, default=None)
    deal_id = WorkspaceRelatedField(Deal, source="deal", allow_null=True, required=False)
    deal_title = serializers.CharField(source="deal.title", read_only=True, default=None)
    customer_id = WorkspaceRelatedField(Customer, source="customer", allow_null=True, required=False)
    customer_name = serializers.CharField(source="customer.name", read_only=True, default=None)
    done = serializers.BooleanField(required=False, help_text="Tick to mark it done (sets done_at); untick to reopen")
    overdue = serializers.SerializerMethodField()

    class Meta:
        model = Activity
        fields = ["id", "kind", "subject", "notes", "due_at", "done", "done_at", "overdue", "assigned_to_id", "assigned_to_name", "lead_id",
                  "lead_name", "deal_id", "deal_title", "customer_id", "customer_name", "created_at"]
        read_only_fields = ["id", "done_at", "overdue", "created_at"]

    def get_overdue(self, obj) -> bool:
        return bool(obj.due_at and not obj.done_at and obj.due_at < timezone.now())

    def to_representation(self, instance):
        data = super().to_representation(instance)
        data["done"] = instance.done_at is not None
        return data

    def validate(self, attrs):
        lead = attrs.get("lead", getattr(self.instance, "lead", None))
        deal = attrs.get("deal", getattr(self.instance, "deal", None))
        customer = attrs.get("customer", getattr(self.instance, "customer", None))
        if not (lead or deal or customer):
            raise serializers.ValidationError({"lead_id": ["Link it to a lead, a deal or a customer."]})
        if deal and not customer and deal.customer_id:
            attrs["customer"] = deal.customer  # a deal's activities also show on its customer
        done = attrs.pop("done", None)
        if done is True and not getattr(self.instance, "done_at", None):
            attrs["done_at"] = timezone.now()
        elif done is False:
            attrs["done_at"] = None
        if attrs.get("kind") == Activity.Kind.NOTE and not self.instance:
            attrs.setdefault("done_at", timezone.now())  # a note is a record, not a to-do
        return attrs
