from drf_spectacular.utils import extend_schema
from rest_framework import generics, status
from rest_framework.response import Response

from apps.auditlogs import services as audit
from apps.bankaccounts.models import BankAccount
from apps.core.exceptions import BusinessRuleError
from apps.core.tenancy import WorkspaceScopedMixin, workspace_object
from apps.journals.models import JournalLine

from . import services
from .models import BankStatementLine
from .serializers import BankStatementLineSerializer, ImportSerializer, LineActionSerializer, SuggestionSerializer


class LineMixin(WorkspaceScopedMixin):
    permission_map = {"GET": "banking.view", "POST": "banking.reconcile"}
    queryset = BankStatementLine.objects.select_related("journal_line__entry", "bank_account")
    serializer_class = BankStatementLineSerializer


class StatementLineListView(LineMixin, generics.ListAPIView):
    filterset_fields = {"bank_account": ["exact"], "status": ["exact"], "line_date": ["gte", "lte"]}
    search_fields = ["description", "reference"]


class StatementImportView(LineMixin, generics.GenericAPIView):
    """Add statement lines (the web app reads the bank's CSV and sends the rows)."""

    pagination_class = None

    serializer_class = ImportSerializer

    @extend_schema(responses={201: BankStatementLineSerializer(many=True)})
    def post(self, request, workspace):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        account = workspace_object(BankAccount, request, pk=serializer.validated_data["bank_account_id"])
        created = services.import_lines(account, serializer.validated_data["rows"])
        audit.record(request, "other", account, {"imported_lines": len(created)})
        return Response(BankStatementLineSerializer(created, many=True).data, status=status.HTTP_201_CREATED)


class SuggestionsView(LineMixin, generics.GenericAPIView):
    """Transactions in the books this line could be."""

    pagination_class = None

    @extend_schema(responses={200: SuggestionSerializer(many=True)})
    def get(self, request, workspace, pk):
        line = workspace_object(BankStatementLine, request, pk=pk)
        return Response(SuggestionSerializer(services.suggestions(line), many=True).data)


class StatementLineActionView(LineMixin, generics.GenericAPIView):
    """match (to a transaction), unmatch, exclude (ignore), include, or record (as an expense or other income)."""

    serializer_class = LineActionSerializer

    @extend_schema(responses={200: BankStatementLineSerializer})
    def post(self, request, workspace, pk):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        d, line = serializer.validated_data, workspace_object(BankStatementLine, request, pk=pk)
        if d["action"] == "match":
            jl = JournalLine.objects.filter(pk=d.get("journal_line_id"), entry__workspace=request.workspace).first()
            if jl is None:
                raise BusinessRuleError("Choose the transaction it matches.")
            services.match(line, jl)
        elif d["action"] == "unmatch":
            services.unmatch(line)
        elif d["action"] in ("exclude", "include"):
            if line.status == BankStatementLine.Status.MATCHED:
                raise BusinessRuleError("Unmatch it first.")
            line.status = "excluded" if d["action"] == "exclude" else "unmatched"
            line.save(update_fields=["status", "updated_at"])
        else:
            if not d.get("account"):
                raise BusinessRuleError("Choose the account to record it in.")
            services.create_transaction(line, account=d["account"], tax_rate=d.get("tax_rate"), description=d.get("description", ""), user=request.user)
        line.refresh_from_db()
        return Response(BankStatementLineSerializer(line).data)
