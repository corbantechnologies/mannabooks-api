from django.db.models import Count, Q
from drf_spectacular.utils import extend_schema
from rest_framework import generics, status
from rest_framework.response import Response

from apps.auditlogs import services as audit
from apps.core.tenancy import WorkspaceScopedMixin, workspace_object

from . import services
from .models import FiscalYear
from .serializers import FiscalYearCreateSerializer, FiscalYearSerializer


class FiscalYearMixin(WorkspaceScopedMixin):
    module = "fiscalyears"
    queryset = FiscalYear.objects.select_related("closed_by")
    serializer_class = FiscalYearSerializer

    def workspace_queryset(self):
        return (
            super().workspace_queryset()
            .annotate(open_periods=Count("periods", filter=Q(periods__status="open")))
            .order_by("-start_date")
        )

    def year(self):
        return workspace_object(self.workspace_queryset(), self.request, pk=self.kwargs["pk"])


class FiscalYearListCreateView(FiscalYearMixin, generics.ListCreateAPIView):
    pagination_class = None

    @extend_schema(request=FiscalYearCreateSerializer, responses={201: FiscalYearSerializer})
    def post(self, request, workspace):
        serializer = FiscalYearCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        year = services.create_adjacent_year(request.workspace, serializer.validated_data["position"], request.user)
        audit.record(request, "create", year)
        self.kwargs["pk"] = year.pk
        return Response(self.get_serializer(self.year()).data, status=status.HTTP_201_CREATED)


class FiscalYearDetailView(FiscalYearMixin, generics.RetrieveAPIView):
    def get_object(self):
        return self.year()


class FiscalYearCloseView(FiscalYearMixin, generics.GenericAPIView):
    """Post the year-end closing entry and close every period of the year."""

    @extend_schema(request=None, responses={200: FiscalYearSerializer})
    def post(self, request, workspace, pk):
        year = services.close_year(self.year(), request.user)
        audit.record(request, "other", year, {"status": "closed"})
        return Response(self.get_serializer(self.year()).data)


class FiscalYearReopenView(FiscalYearMixin, generics.GenericAPIView):
    @extend_schema(request=None, responses={200: FiscalYearSerializer})
    def post(self, request, workspace, pk):
        year = services.reopen_year(self.year(), request.user)
        audit.record(request, "other", year, {"status": "open"})
        return Response(self.get_serializer(self.year()).data)
