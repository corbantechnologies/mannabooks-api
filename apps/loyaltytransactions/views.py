from rest_framework import generics

from apps.core.tenancy import WorkspaceScopedMixin

from .models import LoyaltyTransaction
from .serializers import LoyaltyTransactionSerializer


class LoyaltyTransactionListView(WorkspaceScopedMixin, generics.ListAPIView):
    """Points earned, redeemed, expired and adjusted. Filter by `member`."""

    permission_map = {"GET": "loyalty.view"}
    queryset = LoyaltyTransaction.objects.select_related("member__customer")
    serializer_class = LoyaltyTransactionSerializer
    filterset_fields = ["member", "kind"]
