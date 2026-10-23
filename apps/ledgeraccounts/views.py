from datetime import date

from django.db.models import DecimalField, Q, Sum, Value
from django.db.models.functions import Coalesce
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import generics
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from apps.core.exceptions import BusinessRuleError
from apps.core.money import ZERO
from apps.core.tenancy import WorkspaceScopedMixin, workspace_object
from apps.journals.models import JournalLine

from .models import LedgerAccount
from .serializers import AccountLedgerSerializer, LedgerAccountSerializer

ZERO_DEC = Value(ZERO, output_field=DecimalField(max_digits=18, decimal_places=2))


def parse_date(value, name):
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ValidationError({name: ["Use the format YYYY-MM-DD."]}) from exc


class LedgerAccountMixin(WorkspaceScopedMixin):
    module = "ledgeraccounts"
    queryset = LedgerAccount.objects.all()
    serializer_class = LedgerAccountSerializer

    def workspace_queryset(self):
        from apps.core.scoping import limited_department

        if limited_department(self.request) is not None:  # the accounts, for choosing them; not the whole business's balances
            return super().workspace_queryset().annotate(debit_total=ZERO_DEC, credit_total=ZERO_DEC).order_by("code")
        as_of = parse_date(self.request.query_params.get("as_of"), "as_of")
        posted = ~Q(lines__entry__status="draft")
        if as_of:
            posted &= Q(lines__entry__entry_date__lte=as_of)
        return super().workspace_queryset().annotate(
            debit_total=Coalesce(Sum("lines__debit", filter=posted), ZERO_DEC),
            credit_total=Coalesce(Sum("lines__credit", filter=posted), ZERO_DEC),
        ).order_by("code")  # aggregation drops the model's default ordering


@extend_schema(parameters=[OpenApiParameter("as_of", OpenApiTypes.DATE, description="Balances at this date (default: all time)")])
class LedgerAccountListCreateView(LedgerAccountMixin, generics.ListCreateAPIView):
    filterset_fields = ["account_type", "subtype", "is_active"]
    search_fields = ["code", "name"]
    ordering_fields = ["code", "name"]
    pagination_class = None  # the chart is short and screens need all of it


class LedgerAccountDetailView(LedgerAccountMixin, generics.RetrieveUpdateDestroyAPIView):
    http_method_names = ["get", "patch", "delete"]

    def perform_destroy(self, instance):
        if instance.is_system:
            raise BusinessRuleError("MannaBooks posts to this account automatically; it can't be deleted.")
        if instance.lines.exists():
            raise BusinessRuleError("This account has entries. Deactivate it instead.")
        if instance.children.exists():
            raise BusinessRuleError("Move or delete its sub-accounts first.")
        super().perform_destroy(instance)


class AccountLedgerView(WorkspaceScopedMixin, generics.GenericAPIView):
    """An account's posted lines between two dates, with opening and running balances."""

    module = "ledgeraccounts"
    serializer_class = AccountLedgerSerializer

    @extend_schema(parameters=[
        OpenApiParameter("from", OpenApiTypes.DATE), OpenApiParameter("to", OpenApiTypes.DATE),
    ])
    def get(self, request, workspace, pk):
        from apps.core.scoping import deny_if_limited

        deny_if_limited(request, "An account's ledger")
        account = workspace_object(LedgerAccount, request, pk=pk)
        start = parse_date(request.query_params.get("from"), "from")
        end = parse_date(request.query_params.get("to"), "to")
        sign = 1 if account.is_debit_normal else -1
        lines = JournalLine.objects.filter(account=account).exclude(entry__status="draft").select_related("entry")
        opening = ZERO
        if start:
            before = lines.filter(entry__entry_date__lt=start).aggregate(d=Sum("debit"), c=Sum("credit"))
            opening = sign * ((before["d"] or ZERO) - (before["c"] or ZERO))
            lines = lines.filter(entry__entry_date__gte=start)
        if end:
            lines = lines.filter(entry__entry_date__lte=end)
        running, rows = opening, []
        for line in lines.order_by("entry__entry_date", "entry__posted_at", "line_no"):
            running += sign * (line.debit - line.credit)
            e = line.entry
            rows.append({
                "entry_id": e.id, "number": e.number, "entry_date": e.entry_date,
                "description": line.description or e.description, "reference": e.reference, "source": e.source,
                "debit": line.debit, "credit": line.credit, "balance": running,
            })
        account.debit_total = account.credit_total = None
        data = {"account": account, "from_date": start, "to_date": end, "opening_balance": opening,
                "closing_balance": running, "lines": rows}
        return Response(self.get_serializer(data).data)
