from django.utils import timezone
from drf_spectacular.utils import extend_schema
from rest_framework import generics, status
from rest_framework.response import Response

from apps.auditlogs import services as audit
from apps.core.exceptions import BusinessRuleError
from apps.core.tenancy import WorkspaceScopedMixin, workspace_object

from . import services
from .models import PaymentVoucher
from .serializers import PaymentVoucherSerializer, VoucherActionSerializer


class VoucherMixin(WorkspaceScopedMixin):
    queryset = PaymentVoucher.objects.select_related("supplier", "created_by", "approved_by", "payment").prefetch_related("lines__bill")
    serializer_class = PaymentVoucherSerializer

    def obj(self):
        return workspace_object(self.queryset, self.request, pk=self.kwargs["pk"])

    def respond(self, obj, code=status.HTTP_200_OK):
        self.kwargs["pk"] = obj.pk
        return Response(PaymentVoucherSerializer(self.obj(), context=self.get_serializer_context()).data, status=code)


class PaymentVoucherListCreateView(VoucherMixin, generics.ListCreateAPIView):
    permission_map = {"GET": "paymentvouchers.view", "POST": "paymentvouchers.create"}
    filterset_fields = {"status": ["exact"], "supplier": ["exact"]}
    search_fields = ["number", "supplier__name"]

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        d = serializer.validated_data
        voucher = services.create(request.workspace, supplier=d["supplier"], voucher_date=d.get("voucher_date") or timezone.localdate(),
                                  lines=d["lines"], withholding_amount=d.get("withholding_amount"), notes=d.get("notes", ""), user=request.user)
        audit.record(request, "create", voucher)
        return self.respond(voucher, status.HTTP_201_CREATED)


class PaymentVoucherDetailView(VoucherMixin, generics.RetrieveAPIView):
    permission_map = {"GET": "paymentvouchers.view"}

    def get_object(self):
        return self.obj()


class PaymentVoucherActionView(VoucherMixin, generics.GenericAPIView):
    """approve (paymentvouchers.approve, not by whoever prepared it), pay (supplierpayments.create) or cancel."""

    serializer_class = VoucherActionSerializer

    def required_permission(self, request):
        return {"approve": "paymentvouchers.approve", "pay": "supplierpayments.create"}.get(request.data.get("action"), "paymentvouchers.create")

    @extend_schema(responses={200: PaymentVoucherSerializer})
    def post(self, request, workspace, pk):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        d, voucher = serializer.validated_data, self.obj()
        if d["action"] == "approve":
            voucher = services.approve(voucher, request.user)
        elif d["action"] == "cancel":
            voucher = services.cancel(voucher)
        else:
            if not d.get("paid_from") or not d.get("method"):
                raise BusinessRuleError("Choose how it was paid and the account it was paid from.")
            voucher = services.pay(voucher, payment_date=d.get("payment_date") or timezone.localdate(), method=d["method"],
                                   paid_from=d["paid_from"], reference=d.get("reference", ""), user=request.user)
        audit.record(request, "other", voucher, {"action": d["action"]})
        return self.respond(voucher)
