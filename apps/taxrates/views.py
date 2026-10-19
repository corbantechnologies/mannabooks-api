from django.db import transaction
from rest_framework import generics

from apps.core.tenancy import WorkspaceScopedMixin

from .models import TaxRate
from .serializers import TaxRateSerializer


class TaxRateMixin(WorkspaceScopedMixin):
    module = "taxrates"
    queryset = TaxRate.objects.select_related("sales_account", "purchases_account")
    serializer_class = TaxRateSerializer

    @transaction.atomic
    def _one_default(self, rate):
        if rate.is_default:
            TaxRate.objects.filter(workspace=rate.workspace, is_default=True).exclude(pk=rate.pk).update(is_default=False)


class TaxRateListCreateView(TaxRateMixin, generics.ListCreateAPIView):
    filterset_fields = ["kind", "is_active"]
    search_fields = ["code", "name"]

    def perform_create(self, serializer):
        super().perform_create(serializer)
        self._one_default(serializer.instance)


class TaxRateDetailView(TaxRateMixin, generics.RetrieveUpdateAPIView):
    """Tax rates are deactivated rather than deleted, so past documents keep them."""

    http_method_names = ["get", "patch"]

    def perform_update(self, serializer):
        super().perform_update(serializer)
        self._one_default(serializer.instance)
