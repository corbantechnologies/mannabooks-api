from django.utils import timezone
from drf_spectacular.utils import extend_schema
from rest_framework import generics, status
from rest_framework.response import Response

from apps.auditlogs import services as audit
from apps.core.tenancy import WorkspaceScopedMixin, workspace_object

from . import services
from .models import StockTransfer
from .serializers import StockTransferSerializer


class TransferMixin(WorkspaceScopedMixin):
    module = "inventory"
    queryset = StockTransfer.objects.select_related("from_warehouse", "to_warehouse").prefetch_related("lines__product")
    serializer_class = StockTransferSerializer


class StockTransferListCreateView(TransferMixin, generics.ListCreateAPIView):
    filterset_fields = ["status", "from_warehouse", "to_warehouse"]
    search_fields = ["number", "notes"]

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        d = serializer.validated_data
        transfer = services.create(request.workspace, from_warehouse=d["from_warehouse"], to_warehouse=d["to_warehouse"],
                                   transfer_date=d.get("transfer_date") or timezone.localdate(), rows=d["lines"], notes=d.get("notes", ""), user=request.user)
        audit.record(request, "create", transfer)
        return Response(StockTransferSerializer(self.get_queryset().get(pk=transfer.pk)).data, status=status.HTTP_201_CREATED)


class StockTransferDetailView(TransferMixin, generics.RetrieveAPIView):
    pass


class StockTransferVoidView(TransferMixin, generics.GenericAPIView):
    @extend_schema(request=None, responses={200: StockTransferSerializer})
    def post(self, request, workspace, pk):
        transfer = services.void(workspace_object(StockTransfer, request, pk=pk))
        audit.record(request, "other", transfer, {"void": True})
        return Response(StockTransferSerializer(self.get_queryset().get(pk=pk)).data)
