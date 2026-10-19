from django.utils import timezone
from drf_spectacular.utils import extend_schema
from rest_framework import generics, status
from rest_framework.response import Response

from apps.auditlogs import services as audit
from apps.core.exceptions import BusinessRuleError
from apps.core.tenancy import WorkspaceScopedMixin, workspace_object

from . import services
from .models import PayRun
from .serializers import PayRunActionSerializer, PayRunSerializer


class PayRunMixin(WorkspaceScopedMixin):
    permission_map = {"GET": "payroll.view", "POST": "payroll.manage", "DELETE": "payroll.manage"}
    queryset = PayRun.objects.select_related("approved_by", "paid_from")
    serializer_class = PayRunSerializer


class PayRunListCreateView(PayRunMixin, generics.ListCreateAPIView):
    """Payrolls by month. Creating one makes a payslip for every employee on payroll."""

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        d = serializer.validated_data
        run = services.create(request.workspace, year=d["year"], month=d["month"], pay_date=d.get("pay_date"), user=request.user)
        audit.record(request, "create", run)
        return Response(PayRunSerializer(run).data, status=status.HTTP_201_CREATED)


class PayRunDetailView(PayRunMixin, generics.RetrieveDestroyAPIView):
    def perform_destroy(self, instance):
        if instance.status != PayRun.Status.DRAFT:
            raise BusinessRuleError("Only a draft payroll can be deleted. Reopen it first.")
        super().perform_destroy(instance)


class PayRunActionView(PayRunMixin, generics.GenericAPIView):
    """approve (payroll.approve), reopen, pay (net salaries) or remit (a statutory deduction)."""

    serializer_class = PayRunActionSerializer

    def required_permission(self, request):
        return "payroll.approve" if request.data.get("action") in ("approve", "reopen") else "payroll.manage"

    @extend_schema(responses={200: PayRunSerializer})
    def post(self, request, workspace, pk):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        d, run = serializer.validated_data, workspace_object(PayRun, request, pk=pk)
        when = d.get("date") or timezone.localdate()
        if d["action"] == "approve":
            run = services.approve(run, request.user)
        elif d["action"] == "reopen":
            run = services.reopen(run, request.user)
        else:
            if not d.get("bank_account"):
                raise BusinessRuleError("Choose the account it was paid from.")
            run = (services.pay(run, bank_account=d["bank_account"], paid_on=when, user=request.user) if d["action"] == "pay" else
                   services.remit(run, kind=d.get("kind", ""), bank_account=d["bank_account"], paid_on=when, reference=d.get("reference", ""), user=request.user))
        audit.record(request, "other", run, {"action": d["action"], "kind": d.get("kind")})
        return Response(PayRunSerializer(run).data)
