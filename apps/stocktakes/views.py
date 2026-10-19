from django.utils import timezone
from drf_spectacular.utils import extend_schema
from rest_framework import generics, status
from rest_framework.response import Response

from apps.auditlogs import services as audit
from apps.core.tenancy import WorkspaceScopedMixin, workspace_object

from . import services
from .models import StockTake
from .serializers import CountsSerializer, StockTakeActionSerializer, StockTakeSerializer


class TakeMixin(WorkspaceScopedMixin):
    module = "inventory"
    queryset = StockTake.objects.select_related("warehouse", "category").prefetch_related("lines__product")
    serializer_class = StockTakeSerializer

    def respond(self, take, code=status.HTTP_200_OK):
        return Response(StockTakeSerializer(self.get_queryset().get(pk=take.pk), context=self.get_serializer_context()).data, status=code)


class StockTakeListCreateView(TakeMixin, generics.ListCreateAPIView):
    """Starting a stock take lists every stock product in the warehouse with what the books say."""

    filterset_fields = ["status", "warehouse"]

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        d = serializer.validated_data
        take = services.start(request.workspace, warehouse=d["warehouse"], count_date=d.get("count_date") or timezone.localdate(),
                              category=d.get("category"), notes=d.get("notes", ""), user=request.user)
        audit.record(request, "create", take)
        return self.respond(take, status.HTTP_201_CREATED)


class StockTakeDetailView(TakeMixin, generics.RetrieveAPIView):
    pass


class StockTakeCountsView(TakeMixin, generics.GenericAPIView):
    """Save counts (any number of lines at a time)."""

    serializer_class = CountsSerializer

    @extend_schema(responses={200: StockTakeSerializer})
    def post(self, request, workspace, pk):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        take = services.record_counts(workspace_object(StockTake, request, pk=pk), serializer.validated_data["counts"])
        return self.respond(take)


class StockTakeActionView(TakeMixin, generics.GenericAPIView):
    serializer_class = StockTakeActionSerializer

    @extend_schema(responses={200: StockTakeSerializer})
    def post(self, request, workspace, pk):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        take = workspace_object(StockTake, request, pk=pk)
        take = services.post(take, request.user) if serializer.validated_data["action"] == "post" else services.cancel(take)
        audit.record(request, "other", take, {"action": serializer.validated_data["action"]})
        return self.respond(take)
