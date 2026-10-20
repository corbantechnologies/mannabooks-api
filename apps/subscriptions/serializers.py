from rest_framework import serializers

from apps.plans.models import Plan
from apps.subscriptionpayments.models import SubscriptionPayment

from .models import Subscription

M = {"max_digits": 18, "decimal_places": 2}


class PlanSerializer(serializers.ModelSerializer):
    class Meta:
        model = Plan
        fields = ["id", "key", "name", "description", "price_monthly", "price_yearly", "modules", "features", "max_users", "max_documents_month",
                  "payroll_per_employee", "payroll_minimum", "is_free", "is_public", "is_active", "sort"]


class SubscriptionPaymentSerializer(serializers.ModelSerializer):
    plan_name = serializers.CharField(source="plan.name", read_only=True)
    coupon_code = serializers.CharField(source="coupon.code", read_only=True, default=None)
    business = serializers.CharField(source="subscription.workspace.name", read_only=True)
    business_slug = serializers.CharField(source="subscription.workspace.slug", read_only=True)
    account_number = serializers.CharField(source="subscription.account_number", read_only=True)
    recorded_by_name = serializers.CharField(source="recorded_by.full_name", read_only=True, default=None)

    class Meta:
        model = SubscriptionPayment
        fields = ["id", "business", "business_slug", "account_number", "plan_name", "cycle", "periods", "list_price", "discount", "amount", "coupon_code",
                  "method", "status", "reference", "covers_from", "covers_to", "paid_at", "recorded_by_name", "note", "created_at"]
        read_only_fields = fields


class SubscriptionSerializer(serializers.ModelSerializer):
    plan = PlanSerializer(read_only=True)
    coupon_code = serializers.CharField(source="coupon.code", read_only=True, default=None)

    class Meta:
        model = Subscription
        fields = ["id", "plan", "status", "cycle", "account_number", "trial_ends_on", "paid_until", "complimentary", "discount_percent", "coupon_code",
                  "coupon_payments_left", "created_at"]
        read_only_fields = fields


class PlanUsageSerializer(serializers.Serializer):
    documents_this_month = serializers.IntegerField()
    users = serializers.IntegerField(help_text="Team members using a seat (accountants and self-service staff are free)")


class BillingSerializer(serializers.Serializer):
    subscription = SubscriptionSerializer()
    usage = PlanUsageSerializer()
    plans = PlanSerializer(many=True)
    payments = SubscriptionPaymentSerializer(many=True)
    paybill = serializers.CharField(allow_blank=True, help_text="MannaBooks' paybill number, for paying from the M-Pesa menu")


class QuoteRequestSerializer(serializers.Serializer):
    plan = serializers.SlugField()
    cycle = serializers.ChoiceField(choices=Subscription.Cycle.choices)
    periods = serializers.IntegerField(min_value=1, max_value=24, default=1)
    coupon = serializers.CharField(required=False, allow_blank=True)


class PayRequestSerializer(QuoteRequestSerializer):
    phone = serializers.CharField(max_length=20)


class QuoteSerializer(serializers.Serializer):
    plan = serializers.CharField(source="plan.key")
    cycle = serializers.CharField()
    periods = serializers.IntegerField()
    base = serializers.DecimalField(**M)
    payroll_addon = serializers.DecimalField(**M, help_text="Payroll add-on included in the list price")
    list_price = serializers.DecimalField(**M)
    discount = serializers.DecimalField(**M)
    amount = serializers.DecimalField(**M, help_text="To pay, in whole shillings")
    coupon = serializers.CharField(source="coupon.code", allow_null=True, default=None)
