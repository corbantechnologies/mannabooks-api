from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema
from rest_framework import generics, status
from rest_framework.response import Response

from apps.auditlogs import services as audit
from apps.core.tenancy import WorkspaceScopedMixin
from apps.plans.models import Plan
from apps.subscriptionpayments.models import SubscriptionPayment

from . import services
from .serializers import (
    BillingSerializer,
    PayRequestSerializer,
    QuoteRequestSerializer,
    QuoteSerializer,
    SubscriptionPaymentSerializer,
)


class BillingMixin(WorkspaceScopedMixin):
    """Plan and billing: Owners and Admins. Works while read-only, so an unpaid business can pay."""

    permission_map = {"GET": "workspace.manage", "POST": "workspace.manage"}
    subscription_exempt = True

    def plan(self, key):
        return get_object_or_404(Plan, key=key, is_active=True)


class BillingView(BillingMixin, generics.GenericAPIView):
    serializer_class = BillingSerializer

    def get(self, request, workspace):
        from apps.mpesaconnections.models import MpesaConnection

        sub = services.of(request.workspace)
        home = services.platform_workspace()
        conn = MpesaConnection.objects.filter(workspace=home).first() if home else None
        data = {"subscription": sub, "usage": services.usage(request.workspace),
                "plans": Plan.objects.filter(is_active=True, is_public=True), "payments": sub.payments.select_related("plan", "coupon")[:24],
                "paybill": conn.shortcode if conn else ""}
        return Response(BillingSerializer(data).data)


class QuoteView(BillingMixin, generics.GenericAPIView):
    serializer_class = QuoteRequestSerializer

    @extend_schema(responses={200: QuoteSerializer})
    def post(self, request, workspace):
        s = self.get_serializer(data=request.data)
        s.is_valid(raise_exception=True)
        d = s.validated_data
        q = services.quote(services.of(request.workspace), self.plan(d["plan"]), cycle=d["cycle"], periods=d["periods"], coupon_code=d.get("coupon", ""))
        return Response(QuoteSerializer(q).data)


class PayView(BillingMixin, generics.GenericAPIView):
    serializer_class = PayRequestSerializer

    @extend_schema(responses={201: SubscriptionPaymentSerializer})
    def post(self, request, workspace):
        s = self.get_serializer(data=request.data)
        s.is_valid(raise_exception=True)
        d = s.validated_data
        payment = services.pay_by_mpesa(services.of(request.workspace), self.plan(d["plan"]), cycle=d["cycle"], periods=d["periods"], phone=d["phone"],
                                        coupon_code=d.get("coupon", ""), user=request.user)
        audit.record(request, "other", payment, {"amount": str(payment.amount)})
        return Response(SubscriptionPaymentSerializer(payment).data, status=status.HTTP_201_CREATED)


class PaymentStatusView(BillingMixin, generics.GenericAPIView):
    serializer_class = SubscriptionPaymentSerializer

    def get(self, request, workspace, pk):
        payment = get_object_or_404(SubscriptionPayment, pk=pk, subscription__workspace=request.workspace)
        tx = payment.mpesa_transaction
        if payment.status == "pending" and tx is not None and tx.status in ("failed", "cancelled"):
            payment.status = "failed"
            payment.save(update_fields=["status", "updated_at"])
        return Response(SubscriptionPaymentSerializer(payment).data)


class MoveToFreeView(BillingMixin, generics.GenericAPIView):
    """Stop paying: the business moves to the free plan now. Its records stay; parts outside the plan become read-only."""

    serializer_class = BillingSerializer

    @extend_schema(request=None, responses={200: BillingSerializer})
    def post(self, request, workspace):
        sub = services.move_to_free(services.of(request.workspace))
        audit.record(request, "other", sub, {"plan": "free"})
        return BillingView.get(self, request, workspace)
