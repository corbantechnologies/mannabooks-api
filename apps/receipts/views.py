from drf_spectacular.utils import extend_schema
from rest_framework import generics, status
from rest_framework.response import Response

from apps.auditlogs import services as audit
from apps.core.sales_views import header_from
from apps.core.tenancy import WorkspaceScopedMixin, workspace_object

from . import services
from .models import Receipt
from .serializers import ReceiptSerializer, ReceiptVoidSerializer


class ReceiptMixin(WorkspaceScopedMixin):
    queryset = Receipt.objects.select_related("customer", "deposit_account").prefetch_related("lines__tax_rate", "lines__account")
    serializer_class = ReceiptSerializer

    def receipt(self):
        return workspace_object(self.queryset, self.request, pk=self.kwargs["pk"])

    def respond(self, receipt, code=status.HTTP_200_OK):
        self.kwargs["pk"] = receipt.pk
        return Response(ReceiptSerializer(self.receipt(), context=self.get_serializer_context()).data, status=code)


class ReceiptListCreateView(ReceiptMixin, generics.ListCreateAPIView):
    """Cash sales. Saving one posts it straight away."""

    permission_map = {"GET": "receipts.view", "POST": "receipts.create"}
    filterset_fields = {"status": ["exact"], "customer": ["exact"], "shift": ["exact"], "method": ["exact"], "issue_date": ["gte", "lte"]}
    search_fields = ["number", "customer_name", "payment_reference"]
    ordering_fields = ["issue_date", "number", "total"]

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        d = serializer.validated_data
        receipt = services.create(
            request.workspace, header=header_from(d, request.workspace), rows=d["lines"], method=d["method"],
            deposit_account=d.get("deposit_account"), payment_reference=d.get("payment_reference", ""),
            customer_name=d.get("customer_name", ""), customer_pin=d.get("customer_pin", ""), shift=d.get("shift"), mpesa_prompt=bool(d.get("mpesa_transaction_id")), redeem_points=d.get("redeem_points", 0), user=request.user,
        )
        if d.get("mpesa_transaction_id"):
            from apps.mpesatransactions.services import link_receipt

            link_receipt(receipt, d["mpesa_transaction_id"])
        audit.record(request, "create", receipt)
        return self.respond(receipt, status.HTTP_201_CREATED)


class ReceiptDetailView(ReceiptMixin, generics.RetrieveAPIView):
    permission_map = {"GET": "receipts.view"}

    def get_object(self):
        return self.receipt()


class ReceiptVoidView(ReceiptMixin, generics.GenericAPIView):
    permission_map = {"POST": "receipts.void"}
    serializer_class = ReceiptVoidSerializer

    @extend_schema(responses={200: ReceiptSerializer})
    def post(self, request, workspace, pk):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        receipt = services.void(self.receipt(), serializer.validated_data["reason"], request.user)
        audit.record(request, "other", receipt, {"void": serializer.validated_data["reason"]})
        return self.respond(receipt)
