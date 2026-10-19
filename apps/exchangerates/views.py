from rest_framework import generics

from apps.core.tenancy import WorkspaceScopedMixin

from .models import ExchangeRate
from .serializers import ExchangeRateSerializer


class ExchangeRateMixin(WorkspaceScopedMixin):
    module = "currencies"
    queryset = ExchangeRate.objects.select_related("currency")
    serializer_class = ExchangeRateSerializer


class ExchangeRateListCreateView(ExchangeRateMixin, generics.ListCreateAPIView):
    filterset_fields = ["currency", "rate_date"]
    ordering_fields = ["rate_date"]


class ExchangeRateDetailView(ExchangeRateMixin, generics.RetrieveUpdateDestroyAPIView):
    http_method_names = ["get", "patch", "delete"]
