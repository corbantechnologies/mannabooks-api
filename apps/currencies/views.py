from rest_framework import generics

from apps.core.tenancy import WorkspaceScopedMixin

from .models import Currency
from .serializers import CurrencySerializer


class CurrencyMixin(WorkspaceScopedMixin):
    module = "currencies"
    queryset = Currency.objects.all()
    serializer_class = CurrencySerializer


class CurrencyListCreateView(CurrencyMixin, generics.ListCreateAPIView):
    filterset_fields = ["is_active", "is_base"]
    search_fields = ["code", "name"]


class CurrencyDetailView(CurrencyMixin, generics.RetrieveUpdateAPIView):
    """Currencies are deactivated rather than deleted, so past records keep them."""

    http_method_names = ["get", "patch"]
