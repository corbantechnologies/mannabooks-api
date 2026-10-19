from django.utils import timezone
from drf_spectacular.utils import extend_schema
from rest_framework import generics, status
from rest_framework.response import Response

from apps.auditlogs import services as audit
from apps.core.tenancy import WorkspaceScopedMixin, workspace_object

from . import services
from .models import Expense
from .serializers import ExpenseSerializer, ExpenseVoidSerializer

DETAILS = ("payee", "supplier", "method", "reference", "supplier_etims_number", "notes", "cost_center", "project")


class ExpenseMixin(WorkspaceScopedMixin):
    queryset = Expense.objects.select_related("paid_from", "supplier").prefetch_related("lines__account", "lines__tax_rate", "lines__product")
    serializer_class = ExpenseSerializer

    def respond(self, obj, code=status.HTTP_200_OK):
        return Response(ExpenseSerializer(self.get_queryset().get(pk=obj.pk), context=self.get_serializer_context()).data, status=code)


class ExpenseListCreateView(ExpenseMixin, generics.ListCreateAPIView):
    """Expenses paid straight from a bank, M-Pesa or cash account. Saving posts them."""

    permission_map = {"GET": "banking.view", "POST": "banking.spend"}
    filterset_fields = {"status": ["exact"], "paid_from": ["exact"], "expense_date": ["gte", "lte"]}
    search_fields = ["number", "payee", "reference", "supplier__name"]

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        d = serializer.validated_data
        expense = services.create(request.workspace, paid_from=d["paid_from"], expense_date=d.get("expense_date") or timezone.localdate(),
                                  rows=d["lines"], prices_include_tax=d.get("prices_include_tax", True), user=request.user,
                                  **{k: d[k] for k in DETAILS if k in d})
        audit.record(request, "create", expense)
        return self.respond(expense, status.HTTP_201_CREATED)


class ExpenseDetailView(ExpenseMixin, generics.RetrieveAPIView):
    permission_map = {"GET": "banking.view"}


class ExpenseVoidView(ExpenseMixin, generics.GenericAPIView):
    permission_map = {"POST": "banking.spend"}
    serializer_class = ExpenseVoidSerializer

    @extend_schema(responses={200: ExpenseSerializer})
    def post(self, request, workspace, pk):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        expense = services.void(workspace_object(Expense, request, pk=pk), serializer.validated_data["reason"], request.user)
        audit.record(request, "other", expense, {"void": serializer.validated_data["reason"]})
        return self.respond(expense)
