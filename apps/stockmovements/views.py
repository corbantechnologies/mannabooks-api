from django.db.models import F
from rest_framework import generics

from apps.core.tenancy import WorkspaceScopedMixin

from .models import StockLevel, StockMovement
from .serializers import StockLevelSerializer, StockMovementSerializer


class StockLevelListView(WorkspaceScopedMixin, generics.ListAPIView):
    """Stock on hand by product and warehouse. `?low=true` lists those at or below their reorder level."""

    permission_map = {"GET": "inventory.view"}
    queryset = StockLevel.objects.select_related("product", "warehouse")
    serializer_class = StockLevelSerializer
    filterset_fields = ["warehouse", "product", "product__category"]
    search_fields = ["product__name", "product__code"]

    def workspace_queryset(self):
        qs = super().workspace_queryset().filter(product__track_inventory=True)
        if self.request.query_params.get("low") == "true":
            qs = qs.filter(quantity__lte=F("product__reorder_level"))
        if self.request.query_params.get("in_stock") == "true":
            qs = qs.filter(quantity__gt=0)
        return qs.order_by("product__name", "warehouse__name")


class StockMovementListView(WorkspaceScopedMixin, generics.ListAPIView):
    """The stock card: every movement, newest first. Filter by product and warehouse."""

    permission_map = {"GET": "inventory.view"}
    queryset = StockMovement.objects.select_related("product", "warehouse")
    serializer_class = StockMovementSerializer
    filterset_fields = {"product": ["exact"], "warehouse": ["exact"], "kind": ["exact"], "movement_date": ["gte", "lte"], "source_id": ["exact"]}
