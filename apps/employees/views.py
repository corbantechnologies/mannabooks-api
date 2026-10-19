from drf_spectacular.utils import extend_schema
from rest_framework import generics, status
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response

from apps.core.exceptions import BusinessRuleError
from apps.core.tenancy import WorkspaceScopedMixin, workspace_object
from apps.invitations import services as invitations
from apps.invitations.serializers import InvitationSerializer
from apps.roles.models import Role
from apps.sequences.services import next_value

from .models import Employee
from .serializers import EmployeeInviteSerializer, EmployeeSerializer


class EmployeeMixin(WorkspaceScopedMixin):
    """
    `employees.view` sees everyone; `employees.view_own` (Self-service) sees only their own record.
    Changes need `employees.manage`.
    """

    module = "employees"
    queryset = Employee.objects.none()  # model hint for the schema
    serializer_class = EmployeeSerializer

    def required_permission(self, request):
        return None if request.method == "GET" else "employees.manage"

    def workspace_queryset(self):
        membership = self.request.membership
        qs = Employee.objects.filter(workspace=self.request.workspace).select_related("department", "reports_to")
        if membership.has_perm("employees.view"):
            return qs
        if membership.has_perm("employees.view_own"):
            return qs.filter(membership=membership)
        raise PermissionDenied("Your role does not allow viewing employees.")


class EmployeeListCreateView(EmployeeMixin, generics.ListCreateAPIView):
    filterset_fields = ["status", "department", "branch", "reports_to"]
    search_fields = ["first_name", "last_name", "staff_number", "email", "phone", "job_title"]
    ordering_fields = ["first_name", "staff_number", "hire_date"]

    def perform_create(self, serializer):
        serializer.validated_data["staff_number"] = next_value(self.request.workspace, "employee")
        super().perform_create(serializer)


class EmployeeDetailView(EmployeeMixin, generics.RetrieveUpdateDestroyAPIView):
    http_method_names = ["get", "patch", "delete"]

    def perform_destroy(self, instance):
        if instance.headed_departments.exists():
            raise BusinessRuleError("This employee heads a department. Choose a new head first.")
        super().perform_destroy(instance)


class EmployeeInviteView(WorkspaceScopedMixin, generics.GenericAPIView):
    """Send an employee an invitation to sign in (employee self-service)."""

    serializer_class = EmployeeInviteSerializer
    permission_map = {"POST": "invitations.manage"}

    @extend_schema(responses={201: InvitationSerializer})
    def post(self, request, workspace, pk):
        employee = workspace_object(Employee, request, pk=pk)
        if employee.membership_id:
            raise BusinessRuleError("This employee can already sign in.")
        if not employee.email:
            raise BusinessRuleError("Add the employee's email address first.")
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        role = serializer.validated_data.get("role_id") or Role.objects.get(workspace=request.workspace, slug="self-service")
        invitation = invitations.invite(request, email=employee.email, role=role, employee=employee)
        return Response(InvitationSerializer(invitation, context=self.get_serializer_context()).data, status=status.HTTP_201_CREATED)
