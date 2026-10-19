from drf_spectacular.utils import extend_schema
from rest_framework import generics, status
from rest_framework.response import Response

from apps.auditlogs import services as audit
from apps.core.tenancy import WorkspaceScopedMixin, workspace_object

from . import services
from .models import SupplierPayment
from .serializers import SupplierPaymentSerializer, SupplierPaymentVoidSerializer


class SupplierPaymentMixin(WorkspaceScopedMixin):
    queryset = SupplierPayment.objects.select_related("supplier", "paid_from").prefetch_related("allocations__bill")
    serializer_class = SupplierPaymentSerializer

    def obj(self):
        return workspace_object(self.queryset, self.request, pk=self.kwargs["pk"])

    def respond(self, obj, code=status.HTTP_200_OK):
        self.kwargs["pk"] = obj.pk
        return Response(SupplierPaymentSerializer(self.obj(), context=self.get_serializer_context()).data, status=code)


class SupplierPaymentListCreateView(SupplierPaymentMixin, generics.ListCreateAPIView):
    permission_map = {"GET": "supplierpayments.view", "POST": "supplierpayments.create"}
    filterset_fields = {"status": ["exact"], "supplier": ["exact"], "payment_date": ["gte", "lte"]}
    search_fields = ["number", "supplier__name", "reference"]

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        d = serializer.validated_data
        payment = services.record(request.workspace, supplier=d["supplier"], payment_date=d["payment_date"], amount=d["amount"],
                                  withholding_amount=d.get("withholding_amount", 0), method=d["method"], paid_from=d["paid_from"],
                                  reference=d.get("reference", ""), notes=d.get("notes", ""), allocations=d.get("allocations"), user=request.user)
        audit.record(request, "create", payment)
        return self.respond(payment, status.HTTP_201_CREATED)


class SupplierPaymentDetailView(SupplierPaymentMixin, generics.RetrieveAPIView):
    permission_map = {"GET": "supplierpayments.view"}

    def get_object(self):
        return self.obj()


class SupplierPaymentVoidView(SupplierPaymentMixin, generics.GenericAPIView):
    permission_map = {"POST": "supplierpayments.void"}
    serializer_class = SupplierPaymentVoidSerializer

    @extend_schema(responses={200: SupplierPaymentSerializer})
    def post(self, request, workspace, pk):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        payment = services.void(self.obj(), serializer.validated_data["reason"], request.user)
        audit.record(request, "other", payment, {"void": serializer.validated_data["reason"]})
        return self.respond(payment)
