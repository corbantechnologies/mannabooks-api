from django.db.models import DecimalField, ExpressionWrapper, F, Sum
from rest_framework import generics

from apps.core.exceptions import BusinessRuleError
from apps.core.tenancy import WorkspaceScopedMixin

from .models import Warehouse
from .serializers import WarehouseSerializer
from .services import default_warehouse


class WarehouseMixin(WorkspaceScopedMixin):
    module = "inventory"
    queryset = Warehouse.objects.select_related("branch")
    serializer_class = WarehouseSerializer

    def workspace_queryset(self):
        value = ExpressionWrapper(F("stock_levels__quantity") * F("stock_levels__average_cost"), output_field=DecimalField(max_digits=18, decimal_places=2))
        return super().workspace_queryset().annotate(stock_value=Sum(value)).order_by("-is_default", "name")

    def _one_default(self, warehouse):
        if warehouse.is_default:
            Warehouse.objects.filter(workspace=warehouse.workspace, is_default=True).exclude(pk=warehouse.pk).update(is_default=False)


class WarehouseListCreateView(WarehouseMixin, generics.ListCreateAPIView):
    filterset_fields = ["is_active", "branch"]

    def list(self, request, *args, **kwargs):
        default_warehouse(request.workspace)  # the first visit creates "Main store"
        return super().list(request, *args, **kwargs)

    def perform_create(self, serializer):
        super().perform_create(serializer)
        self._one_default(serializer.instance)


class WarehouseDetailView(WarehouseMixin, generics.RetrieveUpdateDestroyAPIView):
    http_method_names = ["get", "patch", "delete"]

    def perform_update(self, serializer):
        if serializer.instance.is_default and serializer.validated_data.get("is_default") is False:
            raise BusinessRuleError("Make another warehouse the default instead.")
        super().perform_update(serializer)
        self._one_default(serializer.instance)

    def perform_destroy(self, instance):
        from apps.stockmovements.models import StockMovement

        if instance.is_default or StockMovement.objects.filter(warehouse=instance).exists():
            raise BusinessRuleError("This warehouse is the default or has stock history. Deactivate it instead.")
        super().perform_destroy(instance)
