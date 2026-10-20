from django.utils import timezone
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import generics
from rest_framework.response import Response

from apps.core.tenancy import WorkspaceScopedMixin
from apps.ledgeraccounts.views import parse_date

from . import services
from .serializers import (
    AgedReportSerializer,
    BalanceSheetSerializer,
    CategoryReportSerializer,
    PeriodSummarySerializer,
    ProfitAndLossSerializer,
    TrialBalanceSerializer,
    VatSummarySerializer,
)


class TrialBalanceView(WorkspaceScopedMixin, generics.GenericAPIView):
    permission_map = {"GET": "reports.view"}
    serializer_class = TrialBalanceSerializer

    @extend_schema(parameters=[OpenApiParameter("as_of", OpenApiTypes.DATE, description="Default: today")])
    def get(self, request, workspace):
        as_of = parse_date(request.query_params.get("as_of"), "as_of") or timezone.localdate()
        return Response(self.get_serializer(services.trial_balance(request.workspace, as_of)).data)



def _dims(request) -> dict:
    from rest_framework.exceptions import ValidationError

    from apps.branches.models import Branch
    from apps.costcenters.models import CostCenter
    from apps.projects.models import Project

    out = {}
    for key, model in (("cost_center", CostCenter), ("project", Project), ("branch", Branch)):
        value = request.query_params.get(key)
        if value:
            try:
                out[key] = model.objects.get(workspace=request.workspace, pk=value)
            except (model.DoesNotExist, ValueError, Exception) as exc:
                raise ValidationError({key: ["Not found."]}) from exc
    return out


def _range(request):
    from rest_framework.exceptions import ValidationError

    today = timezone.localdate()
    start = parse_date(request.query_params.get("from"), "from") or today.replace(month=1, day=1)
    end = parse_date(request.query_params.get("to"), "to") or today
    if end < start:
        raise ValidationError({"to": ["The end date can't be before the start date."]})
    return start, end


class ProfitAndLossView(WorkspaceScopedMixin, generics.GenericAPIView):
    permission_map = {"GET": "reports.view"}
    serializer_class = ProfitAndLossSerializer

    @extend_schema(parameters=[
        OpenApiParameter("from", OpenApiTypes.DATE, description="Default: 1 January"), OpenApiParameter("to", OpenApiTypes.DATE, description="Default: today"),
        OpenApiParameter("compare", OpenApiTypes.STR, enum=["none", "previous_period", "previous_year"]),
        OpenApiParameter("cost_center", OpenApiTypes.UUID), OpenApiParameter("project", OpenApiTypes.UUID), OpenApiParameter("branch", OpenApiTypes.UUID),
    ])
    def get(self, request, workspace):
        from datetime import timedelta

        start, end = _range(request)
        compare = request.query_params.get("compare", "none")
        c_from = c_to = None
        if compare == "previous_period":
            length = (end - start).days + 1
            c_to = start - timedelta(days=1)
            c_from = c_to - timedelta(days=length - 1)
        elif compare == "previous_year":
            def back(d):
                try:
                    return d.replace(year=d.year - 1)
                except ValueError:  # 29 February
                    return d.replace(year=d.year - 1, day=28)
            c_from, c_to = back(start), back(end)
        data = services.profit_and_loss(request.workspace, from_date=start, to_date=end, compare_from=c_from, compare_to=c_to, **_dims(request))
        return Response(ProfitAndLossSerializer(data).data)


class BalanceSheetView(WorkspaceScopedMixin, generics.GenericAPIView):
    permission_map = {"GET": "reports.view"}
    serializer_class = BalanceSheetSerializer

    @extend_schema(parameters=[OpenApiParameter("as_of", OpenApiTypes.DATE, description="Default: today"),
                               OpenApiParameter("compare_as_of", OpenApiTypes.DATE)])
    def get(self, request, workspace):
        as_of = parse_date(request.query_params.get("as_of"), "as_of") or timezone.localdate()
        compare = parse_date(request.query_params.get("compare_as_of"), "compare_as_of")
        return Response(BalanceSheetSerializer(services.balance_sheet(request.workspace, as_of=as_of, compare_as_of=compare)).data)


class AgedReportView(WorkspaceScopedMixin, generics.GenericAPIView):
    serializer_class = AgedReportSerializer

    def required_permission(self, request):
        return "reports.view"

    @extend_schema(parameters=[OpenApiParameter("as_of", OpenApiTypes.DATE, description="Default: today")])
    def get(self, request, workspace, kind):
        if kind not in ("receivables", "payables"):
            from rest_framework.exceptions import NotFound

            raise NotFound("Use receivables or payables.")
        as_of = parse_date(request.query_params.get("as_of"), "as_of") or timezone.localdate()
        return Response(AgedReportSerializer(services.aged(request.workspace, kind=kind, as_of=as_of)).data)


class VatSummaryView(WorkspaceScopedMixin, generics.GenericAPIView):
    permission_map = {"GET": "reports.view"}
    serializer_class = VatSummarySerializer

    @extend_schema(parameters=[OpenApiParameter("from", OpenApiTypes.DATE), OpenApiParameter("to", OpenApiTypes.DATE)])
    def get(self, request, workspace):
        start, end = _range(request)
        return Response(VatSummarySerializer(services.vat_summary(request.workspace, from_date=start, to_date=end)).data)



class PeriodSummaryView(WorkspaceScopedMixin, generics.GenericAPIView):
    """The dashboard for a month or a financial year: profit, cash, sales, buying, VAT, payroll, balances owed, top sellers."""

    permission_map = {"GET": "reports.view"}
    serializer_class = PeriodSummarySerializer

    @extend_schema(parameters=[OpenApiParameter("from", OpenApiTypes.DATE), OpenApiParameter("to", OpenApiTypes.DATE)])
    def get(self, request, workspace):
        start, end = _range(request)
        return Response(PeriodSummarySerializer(services.period_summary(request.workspace, from_date=start, to_date=end)).data)


class CategoryReportView(WorkspaceScopedMixin, generics.GenericAPIView):
    """Stock value now and sales in the period, per product category."""

    permission_map = {"GET": "reports.view"}
    serializer_class = CategoryReportSerializer

    @extend_schema(parameters=[OpenApiParameter("from", OpenApiTypes.DATE), OpenApiParameter("to", OpenApiTypes.DATE)])
    def get(self, request, workspace):
        start, end = _range(request)
        return Response(CategoryReportSerializer(services.by_category(request.workspace, from_date=start, to_date=end)).data)
