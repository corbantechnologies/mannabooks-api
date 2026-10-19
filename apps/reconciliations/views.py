from drf_spectacular.utils import extend_schema
from rest_framework import generics, status
from rest_framework.response import Response

from apps.auditlogs import services as audit
from apps.core.exceptions import BusinessRuleError
from apps.core.tenancy import WorkspaceScopedMixin, workspace_object

from . import services
from .models import ReconciledLine, Reconciliation
from .serializers import CandidateSerializer, ReconciliationActionSerializer, ReconciliationSerializer, TickSerializer


class RecMixin(WorkspaceScopedMixin):
    permission_map = {"GET": "banking.view", "POST": "banking.reconcile", "DELETE": "banking.reconcile"}
    queryset = Reconciliation.objects.select_related("bank_account__ledger_account", "completed_by")
    serializer_class = ReconciliationSerializer

    def rec(self):
        return workspace_object(Reconciliation, self.request, pk=self.kwargs["pk"])


class ReconciliationListCreateView(RecMixin, generics.ListCreateAPIView):
    """Start one with the statement's date and closing balance; transactions already matched are ticked for you."""

    filterset_fields = ["bank_account", "status"]

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        d = serializer.validated_data
        rec = services.start(d["bank_account"], statement_date=d["statement_date"], statement_balance=d["statement_balance"], user=request.user)
        audit.record(request, "create", rec)
        return Response(ReconciliationSerializer(rec).data, status=status.HTTP_201_CREATED)


class ReconciliationDetailView(RecMixin, generics.RetrieveDestroyAPIView):
    def perform_destroy(self, instance):
        if instance.status != Reconciliation.Status.IN_PROGRESS:
            raise BusinessRuleError("Reopen a finished reconciliation before deleting it.")
        super().perform_destroy(instance)


class ReconciliationLinesView(RecMixin, generics.GenericAPIView):
    """GET: the transactions to tick. POST: tick or untick some."""

    pagination_class = None

    @extend_schema(responses={200: CandidateSerializer(many=True)})
    def get(self, request, workspace, pk):
        rec = self.rec()
        ticked = set(ReconciledLine.objects.filter(reconciliation=rec).values_list("journal_line_id", flat=True))
        lines = list(services.candidates(rec))
        for line in lines:
            line.cleared = line.pk in ticked
        return Response(CandidateSerializer(lines, many=True).data)

    @extend_schema(request=TickSerializer, responses={200: ReconciliationSerializer})
    def post(self, request, workspace, pk):
        serializer = TickSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        rec = services.tick(self.rec(), serializer.validated_data["journal_line_ids"], serializer.validated_data["cleared"])
        return Response(ReconciliationSerializer(rec).data)


class ReconciliationActionView(RecMixin, generics.GenericAPIView):
    serializer_class = ReconciliationActionSerializer

    @extend_schema(responses={200: ReconciliationSerializer})
    def post(self, request, workspace, pk):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        rec = self.rec()
        rec = services.complete(rec, request.user) if serializer.validated_data["action"] == "complete" else services.reopen(rec)
        audit.record(request, "other", rec, {"action": serializer.validated_data["action"]})
        return Response(ReconciliationSerializer(rec).data)
