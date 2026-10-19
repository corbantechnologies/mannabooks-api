from datetime import timedelta

from django.db.models import F
from django.utils import timezone
from drf_spectacular.utils import extend_schema, inline_serializer
from rest_framework import generics, serializers, status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.auditlogs import services as audit
from apps.core.tenancy import WorkspaceScopedMixin

from . import services
from .models import PortalLink
from .serializers import PortalLinkSerializer, PortalPaySerializer


class PortalLinkMixin(WorkspaceScopedMixin):
    permission_map = {"GET": "customers.view", "POST": "customers.manage", "DELETE": "customers.manage"}
    queryset = PortalLink.objects.select_related("customer", "invoice")
    serializer_class = PortalLinkSerializer


class PortalLinkListCreateView(PortalLinkMixin, generics.ListCreateAPIView):
    """Links customers open without signing in. Share the `url` by WhatsApp, SMS or email."""

    filterset_fields = ["customer", "invoice"]

    def perform_create(self, serializer):
        days = serializer.validated_data.pop("days", 30)
        link = serializer.save(workspace=self.request.workspace, created_by=self.request.user, expires_at=timezone.now() + timedelta(days=days))
        audit.record(self.request, "create", link, {"customer": str(link.customer), "invoice": str(link.invoice or "")})


class PortalLinkDetailView(PortalLinkMixin, generics.RetrieveDestroyAPIView):
    """DELETE stops the link working (it is kept for the record)."""

    def perform_destroy(self, instance):
        instance.revoked_at = timezone.now()
        instance.save(update_fields=["revoked_at", "updated_at"])
        audit.record(self.request, "other", instance, {"revoked": True})


PortalData = inline_serializer("PortalData", {"business": serializers.DictField(), "customer": serializers.DictField(),
                                              "scope": serializers.CharField(), "balance": serializers.CharField(),
                                              "invoices": serializers.ListField(child=serializers.DictField()),
                                              "mpesa_available": serializers.BooleanField()})


class PublicPortalView(APIView):
    """What a customer sees at their link (no sign-in)."""

    permission_classes = [AllowAny]
    authentication_classes = []

    @extend_schema(responses={200: PortalData})
    def get(self, request, token):
        link = services.open_link(token)
        PortalLink.objects.filter(pk=link.pk).update(view_count=F("view_count") + 1, last_viewed_at=timezone.now())
        return Response(services.portal_data(link))


class PublicPortalPayView(APIView):
    """Send an M-Pesa prompt to the customer's phone for one of the link's invoices."""

    permission_classes = [AllowAny]
    authentication_classes = []

    @extend_schema(request=PortalPaySerializer, responses={201: inline_serializer("PortalPayment", {"id": serializers.UUIDField(), "status": serializers.CharField()})})
    def post(self, request, token):
        from apps.mpesatransactions.services import request_payment

        link = services.open_link(token)
        serializer = PortalPaySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        d = serializer.validated_data
        invoice = services.invoice_for(link, d["invoice_id"])
        tx = request_payment(link.workspace, phone=d["phone"], amount=d["amount"], invoice=invoice)
        return Response({"id": str(tx.id), "status": tx.status}, status=status.HTTP_201_CREATED)


class PublicPortalPaymentStatusView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    @extend_schema(responses={200: inline_serializer("PortalPaymentStatus", {"status": serializers.CharField(), "mpesa_receipt": serializers.CharField()})})
    def get(self, request, token, pk):
        from apps.core.exceptions import BusinessRuleError
        from apps.mpesatransactions.models import MpesaTransaction

        link = services.open_link(token)
        tx = MpesaTransaction.objects.filter(workspace=link.workspace, pk=pk, invoice__customer=link.customer).first()
        if tx is None:
            raise BusinessRuleError("Payment not found.")
        return Response({"status": tx.status, "mpesa_receipt": tx.mpesa_receipt})
