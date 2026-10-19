from drf_spectacular.utils import extend_schema
from rest_framework import generics, status
from rest_framework.response import Response

from apps.auditlogs import services as audit
from apps.core.tenancy import WorkspaceScopedMixin, workspace_object

from . import services
from .models import Payment
from .serializers import AllocateSerializer, PaymentSerializer, PaymentVoidSerializer


class PaymentMixin(WorkspaceScopedMixin):
    queryset = Payment.objects.select_related("customer", "deposit_account").prefetch_related("allocations__invoice")
    serializer_class = PaymentSerializer

    def payment(self):
        return workspace_object(self.queryset, self.request, pk=self.kwargs["pk"])

    def respond(self, payment, code=status.HTTP_200_OK):
        self.kwargs["pk"] = payment.pk
        return Response(PaymentSerializer(self.payment(), context=self.get_serializer_context()).data, status=code)


class PaymentListCreateView(PaymentMixin, generics.ListCreateAPIView):
    """Recording a payment posts it at once and applies it to the invoices given."""

    permission_map = {"GET": "payments.view", "POST": "payments.create"}
    filterset_fields = {"status": ["exact"], "customer": ["exact"], "method": ["exact"], "payment_date": ["gte", "lte"]}
    search_fields = ["number", "reference", "customer__name"]
    ordering_fields = ["payment_date", "number", "amount"]

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        d = serializer.validated_data
        payment = services.record(
            request.workspace, customer=d["customer"], payment_date=d["payment_date"], amount=d["amount"],
            method=d["method"], deposit_account=d["deposit_account"], reference=d.get("reference", ""),
            notes=d.get("notes", ""), allocations=d.get("allocations", []), user=request.user,
        )
        audit.record(request, "create", payment)
        return self.respond(payment, status.HTTP_201_CREATED)


class PaymentDetailView(PaymentMixin, generics.RetrieveAPIView):
    permission_map = {"GET": "payments.view"}

    def get_object(self):
        return self.payment()


class PaymentAllocateView(PaymentMixin, generics.GenericAPIView):
    """Apply money not yet applied to more of the customer's invoices."""

    permission_map = {"POST": "payments.create"}
    serializer_class = AllocateSerializer

    @extend_schema(responses={200: PaymentSerializer})
    def post(self, request, workspace, pk):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        payment = services.allocate(self.payment(), serializer.validated_data["allocations"])
        audit.record(request, "update", payment, {"allocated": len(serializer.validated_data["allocations"])})
        return self.respond(payment)


class PaymentVoidView(PaymentMixin, generics.GenericAPIView):
    permission_map = {"POST": "payments.void"}
    serializer_class = PaymentVoidSerializer

    @extend_schema(responses={200: PaymentSerializer})
    def post(self, request, workspace, pk):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        payment = services.void(self.payment(), serializer.validated_data["reason"], request.user)
        audit.record(request, "other", payment, {"void": serializer.validated_data["reason"]})
        return self.respond(payment)
