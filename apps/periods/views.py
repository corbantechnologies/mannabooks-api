from drf_spectacular.utils import extend_schema
from rest_framework import generics, serializers
from rest_framework.response import Response

from apps.auditlogs import services as audit
from apps.core.tenancy import WorkspaceScopedMixin, workspace_object

from . import services
from .models import AccountingPeriod
from .serializers import AccountingPeriodSerializer


class PeriodMixin(WorkspaceScopedMixin):
    module = "periods"
    queryset = AccountingPeriod.objects.select_related("fiscal_year", "closed_by")
    serializer_class = AccountingPeriodSerializer

    def period(self):
        return workspace_object(self.queryset, self.request, pk=self.kwargs["pk"])


class PeriodListView(PeriodMixin, generics.ListAPIView):
    filterset_fields = ["fiscal_year", "status"]
    pagination_class = None


class PeriodCloseView(PeriodMixin, generics.GenericAPIView):
    @extend_schema(request=None, responses={200: AccountingPeriodSerializer})
    def post(self, request, workspace, pk):
        period = services.close_period(self.period(), request.user)
        audit.record(request, "other", period, {"status": "closed"})
        return Response(self.get_serializer(period).data)


class PeriodReopenView(PeriodMixin, generics.GenericAPIView):
    @extend_schema(request=None, responses={200: AccountingPeriodSerializer})
    def post(self, request, workspace, pk):
        period = services.reopen_period(self.period(), request.user)
        audit.record(request, "other", period, {"status": "open"})
        return Response(self.get_serializer(period).data)



class OpenForDateSerializer(serializers.Serializer):
    date = serializers.DateField()


class OpenForDateResultSerializer(serializers.Serializer):
    message = serializers.CharField()


class OpenForDateView(WorkspaceScopedMixin, generics.GenericAPIView):
    """Open the books for a date in one step: add missing earlier years, or reopen its closed year and month."""

    permission_map = {"POST": "periods.manage"}
    queryset = AccountingPeriod.objects.all()
    serializer_class = OpenForDateSerializer

    @extend_schema(responses={200: OpenForDateResultSerializer})
    def post(self, request, workspace):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        message = services.open_for(request.workspace, serializer.validated_data["date"], request.user)
        audit.record(request, "other", request.workspace, {"opened_books_for": str(serializer.validated_data["date"]), "result": message})
        return Response({"message": message})
