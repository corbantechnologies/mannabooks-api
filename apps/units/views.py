from rest_framework import generics

from apps.core.exceptions import BusinessRuleError
from apps.core.tenancy import WorkspaceScopedMixin

from .models import Unit
from .serializers import UnitSerializer
from .services import seed_units


class UnitMixin(WorkspaceScopedMixin):
    module = "products"
    queryset = Unit.objects.all()
    serializer_class = UnitSerializer


class UnitListCreateView(UnitMixin, generics.ListCreateAPIView):
    filterset_fields = ["is_active"]
    search_fields = ["name", "abbreviation"]

    def workspace_queryset(self):
        if not Unit.objects.filter(workspace=self.request.workspace).exists():
            seed_units(self.request.workspace)  # workspaces created before units existed
        return super().workspace_queryset()


class UnitDetailView(UnitMixin, generics.RetrieveUpdateDestroyAPIView):
    http_method_names = ["get", "patch", "delete"]

    def perform_update(self, serializer):
        old = serializer.instance.abbreviation
        super().perform_update(serializer)
        if serializer.instance.abbreviation != old:
            from apps.products.models import Product

            Product.objects.filter(workspace=self.request.workspace, unit=old).update(unit=serializer.instance.abbreviation)

    def perform_destroy(self, instance):
        from apps.products.models import Product

        if Product.objects.filter(workspace=instance.workspace, unit=instance.abbreviation).exists():
            raise BusinessRuleError("Products are sold in this unit. Deactivate it instead.")
        super().perform_destroy(instance)
