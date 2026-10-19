from rest_framework import generics

from apps.core.exceptions import BusinessRuleError
from apps.core.tenancy import WorkspaceScopedMixin

from .models import BillOfMaterials
from .serializers import BillOfMaterialsSerializer


class BomMixin(WorkspaceScopedMixin):
    module = "manufacturing"
    queryset = BillOfMaterials.objects.select_related("product").prefetch_related("lines__component")
    serializer_class = BillOfMaterialsSerializer


class BillOfMaterialsListCreateView(BomMixin, generics.ListCreateAPIView):
    filterset_fields = ["is_active", "product"]
    search_fields = ["name", "product__name"]


class BillOfMaterialsDetailView(BomMixin, generics.RetrieveUpdateDestroyAPIView):
    http_method_names = ["get", "patch", "delete"]

    def perform_destroy(self, instance):
        if instance.production_orders.exists():
            raise BusinessRuleError("Production orders use this recipe. Deactivate it instead.")
        super().perform_destroy(instance)
