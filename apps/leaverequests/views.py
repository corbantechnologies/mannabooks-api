from django.db.models import Q
from django.utils import timezone
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import generics, status
from rest_framework.response import Response

from apps.auditlogs import services as audit
from apps.core.exceptions import BusinessRuleError
from apps.core.tenancy import WorkspaceScopedMixin, workspace_object
from apps.employees.models import Employee

from . import services
from .models import LeaveRequest
from .serializers import LeaveBalanceSerializer, LeaveDecisionSerializer, LeaveRequestSerializer


def own_employee(request):
    employee = Employee.objects.filter(workspace=request.workspace, membership=request.membership).first()
    if employee is None:
        raise BusinessRuleError("Your sign-in isn't linked to an employee record. Ask HR to link it.")
    return employee


class LeaveMixin(WorkspaceScopedMixin):
    permission_map = {"GET": "leave.request", "POST": "leave.request"}
    queryset = LeaveRequest.objects.select_related("employee__department", "decided_by")
    serializer_class = LeaveRequestSerializer

    def workspace_queryset(self):
        """HR sees all; supervisors and department heads see their people's; everyone sees their own."""
        qs = super().workspace_queryset()
        m = self.request.membership
        if m.has_perm("leave.view") or m.has_perm("leave.approve"):
            return qs
        me = Employee.objects.filter(workspace=self.request.workspace, membership=m).first()
        if me is None:
            return qs.none()
        return qs.filter(Q(employee=me) | Q(employee__reports_to=me) | Q(employee__department__head=me))


class LeaveRequestListCreateView(LeaveMixin, generics.ListCreateAPIView):
    """Leave requests. `?mine=true` for your own; POST asks for leave (for yourself, or for anyone if you are HR)."""

    filterset_fields = {"status": ["exact"], "employee": ["exact"], "leave_type": ["exact"], "start_date": ["gte", "lte"]}

    def workspace_queryset(self):
        qs = super().workspace_queryset()
        if self.request.query_params.get("mine") == "true":
            qs = qs.filter(employee__membership=self.request.membership)
        return qs

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        d = serializer.validated_data
        employee = d.get("employee")
        if employee is None or employee.membership_id == request.membership.id:
            employee = own_employee(request)
        elif not request.membership.has_perm("leave.approve"):
            raise BusinessRuleError("You can only ask for leave for yourself.")
        req = services.request_leave(employee, leave_type=d["leave_type"], start_date=d["start_date"], end_date=d["end_date"],
                                     reason=d.get("reason", ""), user=request.user)
        audit.record(request, "create", req)
        return Response(LeaveRequestSerializer(req, context=self.get_serializer_context()).data, status=status.HTTP_201_CREATED)


class LeaveDecisionView(LeaveMixin, generics.GenericAPIView):
    serializer_class = LeaveDecisionSerializer

    @extend_schema(responses={200: LeaveRequestSerializer})
    def post(self, request, workspace, pk):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        req = workspace_object(self.workspace_queryset(), request, pk=pk)
        action = serializer.validated_data["action"]
        if action == "cancel":
            if req.employee.membership_id != request.membership.id and not request.membership.has_perm("leave.approve"):
                raise BusinessRuleError("Only the employee or HR can cancel this.")
            req = services.cancel(req)
        else:
            req = services.decide(req, approve=action == "approve", membership=request.membership, note=serializer.validated_data.get("note", ""))
        audit.record(request, "other", req, {"action": action})
        return Response(LeaveRequestSerializer(req, context=self.get_serializer_context()).data)


class LeaveBalanceView(LeaveMixin, generics.GenericAPIView):
    """Annual leave left this year: yours, or everyone's you can see (`?all=true`)."""

    pagination_class = None

    @extend_schema(parameters=[OpenApiParameter("all", bool), OpenApiParameter("year", int)], responses={200: LeaveBalanceSerializer(many=True)})
    def get(self, request, workspace):
        year = int(request.query_params.get("year") or timezone.localdate().year)
        m = request.membership
        if request.query_params.get("all") == "true" and (m.has_perm("leave.view") or m.has_perm("leave.approve")):
            people = Employee.objects.filter(workspace=request.workspace, status__in=["active", "on_leave"])
        else:
            people = [own_employee(request)]
        rows = [{"employee_id": e.id, "employee_name": e.full_name, **services.balance(e, year)} for e in people]
        return Response(LeaveBalanceSerializer(rows, many=True).data)
