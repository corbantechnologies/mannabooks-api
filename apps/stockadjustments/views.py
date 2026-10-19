from django.utils import timezone
from drf_spectacular.utils import extend_schema
from rest_framework import generics, status
from rest_framework.response import Response

from apps.auditlogs import services as audit
from apps.core.tenancy import WorkspaceScopedMixin, workspace_object

from . import services
from .models import StockAdjustment
from .serializers import StockAdjustmentSerializer


class AdjustmentMixin(WorkspaceScopedMixin):
    module = "inventory"
    queryset = StockAdjustment.objects.select_related("warehouse").prefetch_related("lines__product")
    serializer_class = StockAdjustmentSerializer


class StockAdjustmentListCreateView(AdjustmentMixin, generics.ListCreateAPIView):
    """Adjustments, including opening stock. Saving moves the stock and posts its value."""

    filterset_fields = ["status", "warehouse", "reason"]
    search_fields = ["number", "notes"]

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        d = serializer.validated_data
        adj = services.create(request.workspace, warehouse=d["warehouse"], adjustment_date=d.get("adjustment_date") or timezone.localdate(),
                              reason=d["reason"], rows=d["lines"], notes=d.get("notes", ""), user=request.user)
        audit.record(request, "create", adj)
        return Response(StockAdjustmentSerializer(self.get_queryset().get(pk=adj.pk)).data, status=status.HTTP_201_CREATED)


class StockAdjustmentDetailView(AdjustmentMixin, generics.RetrieveAPIView):
    pass


class StockAdjustmentVoidView(AdjustmentMixin, generics.GenericAPIView):
    @extend_schema(request=None, responses={200: StockAdjustmentSerializer})
    def post(self, request, workspace, pk):
        adj = services.void(workspace_object(StockAdjustment, request, pk=pk), request.user)
        audit.record(request, "other", adj, {"void": True})
        return Response(StockAdjustmentSerializer(self.get_queryset().get(pk=pk)).data)
