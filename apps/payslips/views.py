from rest_framework import generics

from apps.core.exceptions import BusinessRuleError
from apps.core.tenancy import WorkspaceScopedMixin

from . import services
from .models import Payslip
from .serializers import PayslipSerializer


class PayslipMixin(WorkspaceScopedMixin):
    """Payroll staff see every payslip; everyone else sees only their own, once the payroll is approved."""

    queryset = Payslip.objects.select_related("pay_run", "employee__department")
    serializer_class = PayslipSerializer

    def required_permission(self, request):
        return "payroll.manage" if request.method != "GET" else None

    def workspace_queryset(self):
        qs = super().workspace_queryset()
        if self.request.query_params.get("mine") == "true" or not self.request.membership.has_perm("payroll.view"):
            qs = qs.filter(employee__membership=self.request.membership, pay_run__status__in=["approved", "paid"])
        return qs.order_by("-pay_run__year", "-pay_run__month", "employee_name")


class PayslipListView(PayslipMixin, generics.ListAPIView):
    filterset_fields = ["pay_run", "employee"]
    search_fields = ["employee_name", "staff_number"]


class PayslipDetailView(PayslipMixin, generics.RetrieveUpdateAPIView):
    """PATCH (draft payroll only): basic salary, unpaid leave days, allowances and deductions; everything else is recalculated."""

    http_method_names = ["get", "patch"]

    def perform_update(self, serializer):
        if serializer.instance.pay_run.status != "draft":
            raise BusinessRuleError("This payroll is approved. Reopen it to change payslips.")
        slip = serializer.save()
        slip.items = [{**i, "amount": float(i["amount"])} for i in slip.items]
        services.recalculate(slip)
        from apps.payruns.services import refresh_totals

        refresh_totals(slip.pay_run)
