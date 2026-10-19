from rest_framework import serializers

from apps.core.fields import WorkspaceRelatedField
from apps.customers.models import Customer

from .models import LoyaltyMember


class LoyaltyMemberSerializer(serializers.ModelSerializer):
    customer_id = WorkspaceRelatedField(Customer, source="customer")
    customer_name = serializers.CharField(source="customer.name", read_only=True)
    customer_phone = serializers.CharField(source="customer.phone", read_only=True)
    tier_name = serializers.CharField(source="tier.name", read_only=True, default=None)
    points_value = serializers.SerializerMethodField(help_text="What the balance is worth as a discount")

    class Meta:
        model = LoyaltyMember
        fields = ["id", "customer_id", "customer_name", "customer_phone", "card_number", "tier_name", "points_balance", "points_value",
                  "lifetime_points", "qualifying_points", "is_active", "created_at"]
        read_only_fields = ["id", "customer_name", "customer_phone", "tier_name", "points_balance", "points_value", "lifetime_points",
                            "qualifying_points", "created_at"]
        extra_kwargs = {"card_number": {"required": False, "allow_blank": True}}

    def get_points_value(self, obj) -> str:
        program = self.context.get("program")
        return str(round(obj.points_balance * program.point_value, 2)) if program else "0.00"

    def validate_customer_id(self, customer):
        if self.instance is None and LoyaltyMember.objects.filter(customer=customer).exists():
            raise serializers.ValidationError("This customer is already a member.")
        return customer

    def validate_card_number(self, value):
        value = value.strip().upper()
        if value:
            clash = LoyaltyMember.objects.filter(workspace=self.context["workspace"], card_number=value)
            if self.instance:
                clash = clash.exclude(pk=self.instance.pk)
            if clash.exists():
                raise serializers.ValidationError("Another member has this card.")
        return value


class AdjustPointsSerializer(serializers.Serializer):
    points = serializers.IntegerField(help_text="Positive to add, negative to remove")
    reason = serializers.CharField(max_length=200)
