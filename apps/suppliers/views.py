from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import generics
from rest_framework.exceptions import NotFound
from rest_framework.response import Response

from apps.core.exceptions import BusinessRuleError
from apps.core.tenancy import WorkspaceScopedMixin
from apps.ledgeraccounts.views import parse_date
from apps.sequences.services import next_value

from . import services
from .models import Supplier
from .serializers import SupplierSerializer, SupplierStatementSerializer


class SupplierMixin(WorkspaceScopedMixin):
    module = "suppliers"
    queryset = Supplier.objects.select_related("withholding_tax_rate")
    serializer_class = SupplierSerializer

    def workspace_queryset(self):
        return services.with_balance(super().workspace_queryset()).order_by("name")


class SupplierListCreateView(SupplierMixin, generics.ListCreateAPIView):
    filterset_fields = ["is_active", "kind"]
    search_fields = ["name", "number", "email", "phone", "kra_pin"]
    ordering_fields = ["name", "number", "created_at"]

    def perform_create(self, serializer):
        serializer.validated_data["number"] = next_value(self.request.workspace, "supplier")
        super().perform_create(serializer)
        serializer.instance = self.workspace_queryset().get(pk=serializer.instance.pk)


class SupplierDetailView(SupplierMixin, generics.RetrieveUpdateDestroyAPIView):
    http_method_names = ["get", "patch", "delete"]

    def perform_destroy(self, instance):
        from apps.bills.models import Bill
        from apps.purchaseorders.models import PurchaseOrder

        if Bill.objects.filter(supplier=instance).exists() or PurchaseOrder.objects.filter(supplier=instance).exists():
            raise BusinessRuleError("This supplier has documents. Deactivate them instead.")
        super().perform_destroy(instance)


class SupplierStatementView(SupplierMixin, generics.GenericAPIView):
    serializer_class = SupplierStatementSerializer

    @extend_schema(parameters=[OpenApiParameter("from", OpenApiTypes.DATE), OpenApiParameter("to", OpenApiTypes.DATE)])
    def get(self, request, workspace, pk):
        supplier = self.get_queryset().filter(pk=pk).first()
        if supplier is None:
            raise NotFound()
        data = services.statement(supplier, parse_date(request.query_params.get("from"), "from"), parse_date(request.query_params.get("to"), "to"))
        return Response(SupplierStatementSerializer({"supplier": supplier, **data}, context=self.get_serializer_context()).data)
