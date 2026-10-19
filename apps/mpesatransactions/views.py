import logging

from django.db.models import Q
from drf_spectacular.utils import extend_schema
from rest_framework import generics, status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.auditlogs import services as audit
from apps.core.tenancy import WorkspaceScopedMixin, workspace_object
from apps.mpesaconnections.models import MpesaConnection

from . import services
from .models import MpesaTransaction
from .serializers import ApplyMpesaSerializer, MpesaTransactionSerializer, PaymentPromptSerializer

log = logging.getLogger(__name__)
ACCEPTED = {"ResultCode": 0, "ResultDesc": "Accepted"}


class MpesaTransactionMixin(WorkspaceScopedMixin):
    queryset = MpesaTransaction.objects.select_related("invoice", "payment", "receipt")
    serializer_class = MpesaTransactionSerializer


class MpesaTransactionListView(MpesaTransactionMixin, generics.ListAPIView):
    """M-Pesa payments seen through Daraja. `?matched=false` lists those not yet recorded."""

    permission_map = {"GET": "payments.view"}
    filterset_fields = ["status", "kind", "invoice"]
    search_fields = ["mpesa_receipt", "phone", "payer_name", "account_reference"]

    def workspace_queryset(self):
        qs = super().workspace_queryset()
        matched = self.request.query_params.get("matched")
        if matched in ("true", "false"):
            unmatched = Q(payment__isnull=True, receipt__isnull=True)
            qs = qs.exclude(unmatched) if matched == "true" else qs.filter(unmatched, status="completed")
        return qs


class MpesaTransactionDetailView(MpesaTransactionMixin, generics.RetrieveAPIView):
    """One transaction; the till and invoice screens poll it while the customer approves the prompt."""

    permission_map = {"GET": "payments.view"}


class PaymentPromptView(MpesaTransactionMixin, generics.GenericAPIView):
    """Send an M-Pesa payment prompt (STK push) to a customer's phone."""

    permission_map = {"POST": "receipts.create"}
    serializer_class = PaymentPromptSerializer

    @extend_schema(responses={201: MpesaTransactionSerializer})
    def post(self, request, workspace):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        d = serializer.validated_data
        tx = services.request_payment(request.workspace, phone=d["phone"], amount=d["amount"], invoice=d.get("invoice"),
                                      reference=d.get("reference", ""), user=request.user)
        return Response(MpesaTransactionSerializer(tx).data, status=status.HTTP_201_CREATED)


class ApplyMpesaView(MpesaTransactionMixin, generics.GenericAPIView):
    permission_map = {"POST": "payments.create"}
    serializer_class = ApplyMpesaSerializer

    @extend_schema(responses={200: MpesaTransactionSerializer})
    def post(self, request, workspace, pk):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        tx = workspace_object(MpesaTransaction, request, pk=pk)
        tx = services.apply(tx, serializer.validated_data["customer"], serializer.validated_data.get("invoice"), request.user)
        audit.record(request, "other", tx, {"applied_to": str(tx.payment)})
        return Response(MpesaTransactionSerializer(tx).data)


class SafaricomCallbackView(APIView):
    """
    Public endpoints Safaricom calls. The token in the URL identifies the workspace; anything unexpected is
    logged and acknowledged, because Safaricom retries callbacks that fail.
    """

    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = []

    @extend_schema(exclude=True)
    def post(self, request, token, hook):
        conn = MpesaConnection.objects.filter(callback_token=token).select_related("workspace").first()
        if conn is None:
            return Response({"ResultCode": 1, "ResultDesc": "Unknown"}, status=status.HTTP_404_NOT_FOUND)
        if hook == "c2b/validation":
            return Response(ACCEPTED)
        try:
            if hook == "stk":
                services.handle_stk_callback(conn, request.data)
            else:
                services.handle_c2b(conn, request.data)
        except Exception:  # never make Safaricom retry forever; the payload is in the logs
            log.exception("M-Pesa %s callback failed for %s: %s", hook, conn.workspace_id, request.data)
        return Response(ACCEPTED)
