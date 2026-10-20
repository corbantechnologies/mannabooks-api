"""The MannaBooks platform admin (/api/v1/platform/): for MannaBooks staff (users with is_staff) only."""
from django.shortcuts import get_object_or_404
from django.utils import timezone
from drf_spectacular.utils import extend_schema
from rest_framework import generics
from rest_framework.permissions import BasePermission, IsAuthenticated
from rest_framework.response import Response

from apps.accounts.models import User
from apps.coupons.models import Coupon
from apps.plans.models import Plan
from apps.subscriptionpayments.models import SubscriptionPayment
from apps.subscriptions import services as subs
from apps.subscriptions.serializers import PlanSerializer, SubscriptionPaymentSerializer
from apps.supporttickets import services as tickets
from apps.supporttickets.models import SupportTicket
from apps.supporttickets.serializers import ReplySerializer, SupportTicketSerializer
from apps.workspaces.models import Workspace

from . import services
from .models import PlatformAction
from .serializers import (
    BusinessActionSerializer,
    BusinessDetailSerializer,
    BusinessSerializer,
    BusinessUsageSerializer,
    CouponSerializer,
    MemberSerializer,
    PaymentActionSerializer,
    PlatformActionSerializer,
    PlatformUserSerializer,
    RenewalSerializer,
    StatsSerializer,
    TicketUpdateSerializer,
    UserActionSerializer,
)


class IsPlatformStaff(BasePermission):
    message = "This is for MannaBooks staff."

    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and request.user.is_staff and request.user.is_active)


class StaffMixin:
    permission_classes = [IsAuthenticated, IsPlatformStaff]


class StatsView(StaffMixin, generics.GenericAPIView):
    serializer_class = StatsSerializer

    def get(self, request):
        return Response(StatsSerializer(services.stats()).data)


class BusinessListView(StaffMixin, generics.ListAPIView):
    serializer_class = BusinessSerializer

    def get_queryset(self):
        p = self.request.query_params
        return services.businesses(p.get("search", "").strip(), p.get("status", ""), p.get("plan", ""))


class BusinessDetailView(StaffMixin, generics.GenericAPIView):
    serializer_class = BusinessDetailSerializer

    def get(self, request, slug):
        ws = get_object_or_404(services.businesses(), slug=slug)
        sub = subs.of(ws)
        usage = {**subs.usage(ws), "last_active": services.last_active(ws)}
        return Response({
            "business": BusinessSerializer(ws).data,
            "usage": BusinessUsageSerializer(usage).data,
            "members": MemberSerializer(ws.memberships.filter(status="active").select_related("user", "role"), many=True).data,
            "payments": SubscriptionPaymentSerializer(sub.payments.select_related("plan", "coupon", "recorded_by", "subscription__workspace")[:50], many=True).data,
            "tickets": SupportTicketSerializer(SupportTicket.objects.filter(workspace=ws)[:20], many=True, context={"staff": True}).data,
            "actions": PlatformActionSerializer(PlatformAction.objects.filter(target_type="workspace", target_id=str(ws.pk))[:30], many=True).data,
        })


class BusinessActionView(StaffMixin, generics.GenericAPIView):
    serializer_class = BusinessActionSerializer

    @extend_schema(responses={200: BusinessSerializer})
    def post(self, request, slug):
        ws = get_object_or_404(Workspace, slug=slug)
        s = self.get_serializer(data=request.data)
        s.is_valid(raise_exception=True)
        d = dict(s.validated_data)
        services.business_action(ws, d.pop("action"), d, request.user)
        return Response(BusinessSerializer(services.businesses().get(pk=ws.pk)).data)


class UserListView(StaffMixin, generics.ListAPIView):
    """Everyone with a MannaBooks login. `show`: full_access, staff or blocked."""

    serializer_class = PlatformUserSerializer

    def get_queryset(self):
        p = self.request.query_params
        return services.users(p.get("search", "").strip(), p.get("show", ""))


class UserActionView(StaffMixin, generics.GenericAPIView):
    """Block or unblock a person, give or take back full access (all their businesses free on the top plan), or staff access."""

    serializer_class = UserActionSerializer

    @extend_schema(responses={200: PlatformUserSerializer})
    def post(self, request, pk):
        s = self.get_serializer(data=request.data)
        s.is_valid(raise_exception=True)
        services.user_action(get_object_or_404(User, pk=pk), s.validated_data["action"], request.user, s.validated_data.get("note", ""))
        return Response(PlatformUserSerializer(services.users().get(pk=pk)).data)


class PlanListCreateView(StaffMixin, generics.ListCreateAPIView):
    serializer_class = PlanSerializer
    queryset = Plan.objects.all()
    pagination_class = None

    def perform_create(self, serializer):
        services.record(self.request.user, "plan_create", serializer.save())


class PlanDetailView(StaffMixin, generics.RetrieveUpdateAPIView):
    serializer_class = PlanSerializer
    queryset = Plan.objects.all()
    http_method_names = ["get", "patch"]

    def perform_update(self, serializer):
        services.record(self.request.user, "plan_update", serializer.save(), {k: str(v) for k, v in serializer.validated_data.items()})


class CouponListCreateView(StaffMixin, generics.ListCreateAPIView):
    serializer_class = CouponSerializer
    queryset = Coupon.objects.prefetch_related("plans")

    def perform_create(self, serializer):
        services.record(self.request.user, "coupon_create", serializer.save())


class CouponDetailView(StaffMixin, generics.RetrieveUpdateAPIView):
    serializer_class = CouponSerializer
    queryset = Coupon.objects.prefetch_related("plans")
    http_method_names = ["get", "patch"]

    def perform_update(self, serializer):
        services.record(self.request.user, "coupon_update", serializer.save())


class PaymentListView(StaffMixin, generics.ListAPIView):
    """Subscription payments. `reconcile=true`: payments waiting for staff (part payments, unclear paybill payments)."""

    serializer_class = SubscriptionPaymentSerializer
    filterset_fields = ["status", "method"]
    search_fields = ["reference", "subscription__account_number", "subscription__workspace__name"]

    def get_queryset(self):
        qs = SubscriptionPayment.objects.select_related("plan", "coupon", "recorded_by", "subscription__workspace")
        if self.request.query_params.get("reconcile") == "true":
            qs = qs.filter(status="pending").exclude(note="")
        return qs


class PaymentActionView(StaffMixin, generics.GenericAPIView):
    serializer_class = PaymentActionSerializer

    @extend_schema(responses={200: SubscriptionPaymentSerializer})
    def post(self, request, pk):
        payment = get_object_or_404(SubscriptionPayment, pk=pk)
        s = self.get_serializer(data=request.data)
        s.is_valid(raise_exception=True)
        d = dict(s.validated_data)
        services.payment_action(payment, d.pop("action"), d, request.user)
        payment.refresh_from_db()
        return Response(SubscriptionPaymentSerializer(payment).data)


class TicketListView(StaffMixin, generics.ListAPIView):
    serializer_class = SupportTicketSerializer
    filterset_fields = ["status", "priority", "category"]
    search_fields = ["number", "subject", "workspace__name", "raised_by__email"]

    def get_queryset(self):
        qs = tickets.visible_to(self.request.user, staff=True)
        if self.request.query_params.get("mine") == "true":
            qs = qs.filter(assigned_to=self.request.user)
        return qs

    def get_serializer_context(self):
        return {**super().get_serializer_context(), "staff": True}


class TicketDetailView(StaffMixin, generics.GenericAPIView):
    serializer_class = TicketUpdateSerializer

    @extend_schema(responses={200: SupportTicketSerializer})
    def get(self, request, pk):
        return Response(SupportTicketSerializer(get_object_or_404(SupportTicket, pk=pk), context={"staff": True}).data)

    @extend_schema(responses={200: SupportTicketSerializer})
    def patch(self, request, pk):
        ticket = get_object_or_404(SupportTicket, pk=pk)
        s = self.get_serializer(data=request.data)
        s.is_valid(raise_exception=True)
        d = s.validated_data
        if "status" in d:
            ticket.status = d["status"]
            ticket.resolved_at = timezone.now() if d["status"] in ("resolved", "closed") else None
        if "priority" in d:
            ticket.priority = d["priority"]
        if d.get("assign_to_me"):
            ticket.assigned_to = request.user
        ticket.save()
        services.record(request.user, "ticket_update", ticket, {k: str(v) for k, v in d.items()})
        return Response(SupportTicketSerializer(ticket, context={"staff": True}).data)


class TicketReplyView(StaffMixin, generics.GenericAPIView):
    serializer_class = ReplySerializer

    @extend_schema(responses={200: SupportTicketSerializer})
    def post(self, request, pk):
        ticket = get_object_or_404(SupportTicket, pk=pk)
        s = self.get_serializer(data=request.data)
        s.is_valid(raise_exception=True)
        ticket = tickets.reply(ticket, request.user, s.validated_data["body"], staff=True, internal=s.validated_data["internal"])
        return Response(SupportTicketSerializer(ticket, context={"staff": True}).data)


class ActionLogView(StaffMixin, generics.ListAPIView):
    serializer_class = PlatformActionSerializer
    queryset = PlatformAction.objects.select_related("actor")
    filterset_fields = ["action", "target_type"]


class RenewalListView(StaffMixin, generics.GenericAPIView):
    """Trials ending and plans renewing in the next `days` (default 14), and businesses already behind."""

    serializer_class = RenewalSerializer
    pagination_class = None

    @extend_schema(responses={200: RenewalSerializer(many=True)})
    def get(self, request):
        from apps.subscriptions.reminders import upcoming

        days = min(int(request.query_params.get("days") or 14), 90)
        return Response(RenewalSerializer(upcoming(days), many=True).data)
