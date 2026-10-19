from django.utils import timezone
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import generics
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from apps.auditlogs import services as audit
from apps.core.tenancy import WorkspaceScopedMixin, workspace_object
from apps.costcenters.models import CostCenter
from apps.ledgeraccounts.models import LedgerAccount
from apps.ledgeraccounts.views import parse_date
from apps.projects.models import Project

from . import services
from .models import Budget
from .serializers import BudgetActionSerializer, BudgetCheckSerializer, BudgetSerializer, BudgetVersusActualSerializer


class BudgetMixin(WorkspaceScopedMixin):
    module = "budgets"
    queryset = Budget.objects.select_related("fiscal_year", "cost_center", "project", "approved_by").prefetch_related("lines__account")
    serializer_class = BudgetSerializer


class BudgetListCreateView(BudgetMixin, generics.ListCreateAPIView):
    filterset_fields = ["status", "fiscal_year", "cost_center", "project"]
    search_fields = ["name"]


class BudgetDetailView(BudgetMixin, generics.RetrieveUpdateDestroyAPIView):
    http_method_names = ["get", "patch", "delete"]

    def perform_destroy(self, instance):
        if instance.status != Budget.Status.DRAFT:
            from apps.core.exceptions import BusinessRuleError

            raise BusinessRuleError("Reopen the budget before deleting it.")
        super().perform_destroy(instance)


class BudgetActionView(BudgetMixin, generics.GenericAPIView):
    """approve (budgets.approve, or through the approval chain), reopen (budgets.approve) or fill_from_last_year."""

    serializer_class = BudgetActionSerializer

    def required_permission(self, request):
        return "budgets.approve" if request.data.get("action") in ("approve", "reopen") else "budgets.manage"

    @extend_schema(responses={200: BudgetSerializer})
    def post(self, request, workspace, pk):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        d = serializer.validated_data
        budget = workspace_object(Budget, request, pk=pk)
        if d["action"] == "approve":
            budget = services.approve(budget, request.user)
        elif d["action"] == "reopen":
            budget = services.reopen(budget)
        else:
            budget = services.fill_from_last_year(budget, d.get("uplift_percent") or 0)
        audit.record(request, "other", budget, {"action": d["action"]})
        return Response(BudgetSerializer(self.get_queryset().get(pk=budget.pk), context=self.get_serializer_context()).data)


class BudgetVersusActualView(BudgetMixin, generics.GenericAPIView):
    serializer_class = BudgetVersusActualSerializer

    @extend_schema(parameters=[OpenApiParameter("through", OpenApiTypes.DATE, description="Year to date up to this month (default: today)")])
    def get(self, request, workspace, pk):
        budget = workspace_object(Budget.objects.select_related("fiscal_year"), request, pk=pk)
        through = parse_date(request.query_params.get("through"), "through")
        return Response(BudgetVersusActualSerializer(services.versus_actual(budget, through)).data)


class BudgetCheckView(WorkspaceScopedMixin, generics.GenericAPIView):
    """What's left in the approved budget for an expense account (shown while entering a purchase)."""

    queryset = Budget.objects.all()
    serializer_class = BudgetCheckSerializer

    @extend_schema(parameters=[
        OpenApiParameter("account", OpenApiTypes.UUID, required=True), OpenApiParameter("date", OpenApiTypes.DATE),
        OpenApiParameter("amount", OpenApiTypes.NUMBER), OpenApiParameter("cost_center", OpenApiTypes.UUID),
        OpenApiParameter("project", OpenApiTypes.UUID),
    ])
    def get(self, request, workspace):
        q = request.query_params
        try:
            account = LedgerAccount.objects.get(workspace=request.workspace, pk=q.get("account"))
            cost_center = CostCenter.objects.get(workspace=request.workspace, pk=q["cost_center"]) if q.get("cost_center") else None
            project = Project.objects.get(workspace=request.workspace, pk=q["project"]) if q.get("project") else None
            amount = q.get("amount") or 0
            float(amount)
        except (LedgerAccount.DoesNotExist, CostCenter.DoesNotExist, Project.DoesNotExist, ValueError, Exception) as exc:
            raise ValidationError({"account": ["Unknown account, cost centre or project."]}) from exc
        on = parse_date(q.get("date"), "date") or timezone.localdate()
        return Response(BudgetCheckSerializer(services.check(request.workspace, account=account, on=on, amount=amount,
                                                             cost_center=cost_center, project=project)).data)
