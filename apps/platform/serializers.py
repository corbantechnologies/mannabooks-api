from rest_framework import serializers

from apps.coupons.models import Coupon
from apps.plans.models import Plan

from .models import PlatformAction

M = {"max_digits": 18, "decimal_places": 2}


class StatsSerializer(serializers.Serializer):
    businesses = serializers.IntegerField()
    new_this_month = serializers.IntegerField()
    trialing = serializers.IntegerField()
    paying = serializers.IntegerField()
    free = serializers.IntegerField()
    complimentary = serializers.IntegerField()
    past_due = serializers.IntegerField()
    blocked = serializers.IntegerField()
    mrr = serializers.DecimalField(**M, help_text="Monthly recurring revenue from paying businesses")
    collected_this_month = serializers.DecimalField(**M)
    payments_to_reconcile = serializers.IntegerField()
    open_tickets = serializers.IntegerField()
    urgent_tickets = serializers.IntegerField()


class BusinessSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    name = serializers.CharField()
    slug = serializers.CharField()
    kra_pin = serializers.CharField(allow_blank=True)
    phone = serializers.CharField(allow_blank=True)
    email = serializers.CharField(allow_blank=True)
    owner_name = serializers.CharField(source="owner.full_name")
    owner_email = serializers.CharField(source="owner.email")
    owner_id = serializers.UUIDField(source="owner.id")
    owner_full_access = serializers.BooleanField(source="owner.full_access")
    members = serializers.IntegerField(default=0)
    plan = serializers.CharField(source="subscription.plan.name", default=None)
    plan_key = serializers.CharField(source="subscription.plan.key", default=None)
    status = serializers.CharField(source="subscription.status", default=None)
    account_number = serializers.CharField(source="subscription.account_number", default=None)
    trial_ends_on = serializers.DateField(source="subscription.trial_ends_on", default=None)
    paid_until = serializers.DateField(source="subscription.paid_until", default=None)
    complimentary = serializers.BooleanField(source="subscription.complimentary", default=False)
    complimentary_until = serializers.DateField(source="subscription.complimentary_until", default=None)
    discount_percent = serializers.DecimalField(source="subscription.discount_percent", max_digits=5, decimal_places=2, default=0)
    notes = serializers.CharField(source="subscription.notes", default="")
    blocked_at = serializers.DateTimeField(allow_null=True)
    blocked_reason = serializers.CharField(allow_blank=True)
    is_active = serializers.BooleanField()
    created_at = serializers.DateTimeField()


class MemberSerializer(serializers.Serializer):
    user_id = serializers.UUIDField(source="user.id")
    name = serializers.CharField(source="user.full_name")
    email = serializers.CharField(source="user.email")
    phone = serializers.CharField(source="user.phone")
    role = serializers.CharField(source="role.name")
    user_active = serializers.BooleanField(source="user.is_active")
    last_login = serializers.DateTimeField(source="user.last_login", allow_null=True)


class BusinessUsageSerializer(serializers.Serializer):
    documents_this_month = serializers.IntegerField()
    users = serializers.IntegerField()
    last_active = serializers.DateTimeField(allow_null=True)


class BusinessActionSerializer(serializers.Serializer):
    action = serializers.ChoiceField(choices=["block", "unblock", "change_plan", "extend_trial", "set_discount", "set_complimentary", "record_payment",
                                              "move_to_free", "note", "send_reminder"])
    until = serializers.DateField(required=False, allow_null=True, help_text="set_complimentary: the last free day; blank: until ended")
    reason = serializers.CharField(required=False, allow_blank=True)
    plan = serializers.CharField(required=False, allow_blank=True)
    days = serializers.IntegerField(required=False)
    discount_percent = serializers.DecimalField(max_digits=5, decimal_places=2, required=False)
    complimentary = serializers.BooleanField(required=False)
    cycle = serializers.ChoiceField(choices=["monthly", "yearly"], required=False)
    periods = serializers.IntegerField(required=False, min_value=1, max_value=36)
    amount = serializers.DecimalField(**M, required=False)
    method = serializers.ChoiceField(choices=["mpesa", "bank", "cash", "credit"], required=False)
    reference = serializers.CharField(required=False, allow_blank=True)
    note = serializers.CharField(required=False, allow_blank=True)
    notes = serializers.CharField(required=False, allow_blank=True)


class PaymentActionSerializer(serializers.Serializer):
    action = serializers.ChoiceField(choices=["complete", "fail", "refund"])
    periods = serializers.IntegerField(required=False, min_value=1, max_value=36)
    reference = serializers.CharField(required=False, allow_blank=True)
    note = serializers.CharField(required=False, allow_blank=True)


class UserActionSerializer(serializers.Serializer):
    action = serializers.ChoiceField(choices=["block", "unblock", "grant_full_access", "revoke_full_access", "make_staff", "remove_staff"])
    note = serializers.CharField(required=False, allow_blank=True, max_length=255)


class PlatformUserSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    full_name = serializers.CharField()
    email = serializers.CharField()
    phone = serializers.CharField(allow_blank=True)
    is_active = serializers.BooleanField()
    is_staff = serializers.BooleanField()
    is_superuser = serializers.BooleanField()
    full_access = serializers.BooleanField()
    full_access_note = serializers.CharField(allow_blank=True)
    businesses = serializers.IntegerField(default=0, help_text="Businesses they own")
    memberships_count = serializers.IntegerField(default=0, help_text="Businesses they belong to")
    date_joined = serializers.DateTimeField()
    last_login = serializers.DateTimeField(allow_null=True)


class CouponSerializer(serializers.ModelSerializer):
    plan_keys = serializers.SlugRelatedField(source="plans", slug_field="key", queryset=Plan.objects.all(), many=True, required=False)

    class Meta:
        model = Coupon
        fields = ["id", "code", "description", "percent_off", "amount_off", "payments", "plan_keys", "valid_until", "max_redemptions", "times_redeemed",
                  "is_active", "created_at"]
        read_only_fields = ["id", "times_redeemed", "created_at"]

    def validate_code(self, value):
        return value.strip().upper()

    def validate(self, attrs):
        if attrs.get("percent_off") is not None and not 0 <= attrs["percent_off"] <= 100:
            raise serializers.ValidationError({"percent_off": ["Use 0 to 100."]})
        return attrs


class PlatformActionSerializer(serializers.ModelSerializer):
    actor_name = serializers.CharField(source="actor.full_name", read_only=True, default=None)

    class Meta:
        model = PlatformAction
        fields = ["id", "actor_name", "action", "target_type", "target_id", "target_label", "details", "created_at"]
        read_only_fields = fields


class TicketUpdateSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=["open", "waiting", "resolved", "closed"], required=False)
    priority = serializers.ChoiceField(choices=["low", "normal", "high", "urgent"], required=False)
    assign_to_me = serializers.BooleanField(required=False)


class BusinessDetailSerializer(serializers.Serializer):
    business = BusinessSerializer()
    usage = BusinessUsageSerializer()
    members = MemberSerializer(many=True)
    payments = serializers.ListField(child=serializers.DictField())
    tickets = serializers.ListField(child=serializers.DictField())
    actions = PlatformActionSerializer(many=True)


class RenewalSerializer(serializers.Serializer):
    business = serializers.CharField(source="workspace.name")
    slug = serializers.CharField(source="workspace.slug")
    owner_email = serializers.CharField(source="workspace.owner.email")
    plan = serializers.CharField(source="plan.name")
    status = serializers.CharField()
    trial_ends_on = serializers.DateField(allow_null=True)
    paid_until = serializers.DateField(allow_null=True)
    account_number = serializers.CharField()
    reminders_sent = serializers.ListField(child=serializers.CharField())
