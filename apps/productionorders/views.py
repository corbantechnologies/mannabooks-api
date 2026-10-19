from django.utils import timezone
from drf_spectacular.utils import extend_schema
from rest_framework import generics, status
from rest_framework.response import Response

from apps.auditlogs import services as audit
from apps.core.tenancy import WorkspaceScopedMixin, workspace_object
from apps.warehouses.services import default_warehouse

from . import services
from .models import ProductionOrder
from .serializers import ProductionActionSerializer, ProductionOrderSerializer


class ProductionMixin(WorkspaceScopedMixin):
    module = "manufacturing"
    queryset = ProductionOrder.objects.select_related("bom__product", "warehouse").prefetch_related("lines__component")
    serializer_class = ProductionOrderSerializer

    def respond(self, order, code=status.HTTP_200_OK):
        return Response(ProductionOrderSerializer(self.get_queryset().get(pk=order.pk), context=self.get_serializer_context()).data, status=code)


class ProductionOrderListCreateView(ProductionMixin, generics.ListCreateAPIView):
    filterset_fields = ["status", "bom"]
    search_fields = ["number", "bom__product__name"]

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        d = serializer.validated_data
        order = services.plan(request.workspace, bom=d["bom"], quantity=d["quantity"], warehouse=d.get("warehouse") or default_warehouse(request.workspace),
                              production_date=d.get("production_date") or timezone.localdate(), notes=d.get("notes", ""), user=request.user)
        audit.record(request, "create", order)
        return self.respond(order, status.HTTP_201_CREATED)


class ProductionOrderDetailView(ProductionMixin, generics.RetrieveAPIView):
    pass


class ProductionOrderActionView(ProductionMixin, generics.GenericAPIView):
    serializer_class = ProductionActionSerializer

    @extend_schema(responses={200: ProductionOrderSerializer})
    def post(self, request, workspace, pk):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        d, order = serializer.validated_data, workspace_object(ProductionOrder, request, pk=pk)
        if d["action"] == "complete":
            if d.get("usage"):
                services.set_usage(order, d["usage"])
            order = services.complete(order)
        else:
            order = services.cancel(order)
        audit.record(request, "other", order, {"action": d["action"]})
        return self.respond(order)
