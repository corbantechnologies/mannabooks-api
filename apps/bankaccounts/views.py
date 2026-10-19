from django.db.models import Count, Max, Q
from rest_framework import generics

from apps.auditlogs import services as audit
from apps.core.exceptions import BusinessRuleError
from apps.core.tenancy import WorkspaceScopedMixin

from . import services
from .models import BankAccount
from .serializers import BankAccountSerializer


class BankAccountMixin(WorkspaceScopedMixin):
    module = "banking"
    queryset = BankAccount.objects.select_related("ledger_account")
    serializer_class = BankAccountSerializer

    def workspace_queryset(self):
        return super().workspace_queryset().annotate(
            unmatched_lines=Count("statement_lines", filter=Q(statement_lines__status="unmatched"), distinct=True),
            last_reconciled=Max("reconciliations__statement_date", filter=Q(reconciliations__status="completed")),
        ).order_by("name")


class BankAccountListCreateView(BankAccountMixin, generics.ListCreateAPIView):
    """Bank, M-Pesa and cash accounts with their balances. Creating one adds its ledger account."""

    filterset_fields = ["is_active", "kind"]

    def list(self, request, *args, **kwargs):
        services.sync(request.workspace)
        return super().list(request, *args, **kwargs)

    def perform_create(self, serializer):
        d = serializer.validated_data
        account = services.create(self.request.workspace, user=self.request.user, **d)
        audit.record(self.request, "create", account)
        serializer.instance = self.workspace_queryset().get(pk=account.pk)


class BankAccountDetailView(BankAccountMixin, generics.RetrieveUpdateAPIView):
    http_method_names = ["get", "patch"]

    def perform_update(self, serializer):
        super().perform_update(serializer)
        account = serializer.instance
        if account.ledger_account.name != account.name or account.ledger_account.is_active != account.is_active:
            if not account.is_active and services.balance(account) != 0:
                raise BusinessRuleError("Move the money out before closing this account; its balance isn't zero.")
            account.ledger_account.name, account.ledger_account.is_active = account.name, account.is_active
            account.ledger_account.save(update_fields=["name", "is_active", "updated_at"])
