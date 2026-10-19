from django.db.models import Count
from rest_framework import generics

from apps.core.tenancy import WorkspaceScopedMixin

from .models import LoyaltyTier
from .serializers import LoyaltyTierSerializer


class TierMixin(WorkspaceScopedMixin):
    module = "loyalty"
    queryset = LoyaltyTier.objects.all()
    serializer_class = LoyaltyTierSerializer

    def workspace_queryset(self):
        return super().workspace_queryset().annotate(member_count=Count("members")).order_by("min_points")

    def perform_create(self, serializer):
        super().perform_create(serializer)
        self._regrade()

    def perform_update(self, serializer):
        super().perform_update(serializer)
        self._regrade()

    def perform_destroy(self, instance):
        super().perform_destroy(instance)
        self._regrade()

    def _regrade(self):
        from apps.loyaltytransactions.services import regrade_all

        regrade_all(self.request.workspace)


class LoyaltyTierListCreateView(TierMixin, generics.ListCreateAPIView):
    pass


class LoyaltyTierDetailView(TierMixin, generics.RetrieveUpdateDestroyAPIView):
    http_method_names = ["get", "patch", "delete"]
