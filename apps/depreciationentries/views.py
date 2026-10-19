from django.utils import timezone
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import generics
from rest_framework.response import Response

from apps.auditlogs import services as audit
from apps.core.tenancy import WorkspaceScopedMixin
from apps.ledgeraccounts.views import parse_date

from . import services
from .models import DepreciationEntry
from .serializers import (
    DepreciationPreviewSerializer,
    DepreciationRunSerializer,
    RunRequestSerializer,
    RunResultSerializer,
)


class DepreciationRunsView(WorkspaceScopedMixin, generics.GenericAPIView):
    """Depreciation runs so far, latest first."""

    permission_map = {"GET": "fixedassets.view"}
    queryset = DepreciationEntry.objects.all()
    serializer_class = DepreciationRunSerializer
    pagination_class = None

    @extend_schema(responses={200: DepreciationRunSerializer(many=True)})
    def get(self, request, workspace):
        return Response(DepreciationRunSerializer(services.runs(request.workspace), many=True).data)


class DepreciationPreviewView(WorkspaceScopedMixin, generics.GenericAPIView):
    permission_map = {"GET": "fixedassets.view"}
    queryset = DepreciationEntry.objects.all()
    serializer_class = DepreciationPreviewSerializer
    pagination_class = None

    @extend_schema(parameters=[OpenApiParameter("month", OpenApiTypes.DATE, description="Any day in the last month to depreciate")],
                   responses={200: DepreciationPreviewSerializer(many=True)})
    def get(self, request, workspace):
        month = parse_date(request.query_params.get("month"), "month") or timezone.localdate()
        return Response(DepreciationPreviewSerializer(services.preview(request.workspace, month), many=True).data)


class DepreciationRunView(WorkspaceScopedMixin, generics.GenericAPIView):
    permission_map = {"POST": "fixedassets.depreciate"}
    queryset = DepreciationEntry.objects.all()
    serializer_class = RunRequestSerializer

    @extend_schema(responses={200: RunResultSerializer})
    def post(self, request, workspace):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        result = services.run(request.workspace, serializer.validated_data["month"], request.user)
        audit.record(request, "other", request.workspace, {"depreciation_run": str(result["month"]), "total": str(result["total"])})
        return Response(RunResultSerializer(result).data)


class DepreciationUndoView(WorkspaceScopedMixin, generics.GenericAPIView):
    permission_map = {"POST": "fixedassets.depreciate"}
    queryset = DepreciationEntry.objects.all()
    serializer_class = RunRequestSerializer

    @extend_schema(responses={204: None})
    def post(self, request, workspace):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        services.undo(request.workspace, serializer.validated_data["month"], request.user)
        audit.record(request, "other", request.workspace, {"depreciation_undone": str(serializer.validated_data["month"])})
        return Response(status=204)
