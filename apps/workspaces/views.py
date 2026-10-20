from django.conf import settings
from rest_framework import generics
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.auditlogs import services as audit
from apps.core.exceptions import BusinessRuleError
from apps.core.tenancy import WorkspacePermission
from apps.taxrates.services import match_default_to_vat_status

from . import services
from .models import Workspace
from .serializers import MyWorkspaceSerializer, WorkspaceContextSerializer, WorkspaceSerializer


class WorkspaceListCreateView(generics.ListCreateAPIView):
    """The caller's workspaces; creating one makes the caller its Owner."""

    permission_classes = [IsAuthenticated]
    queryset = Workspace.objects.none()  # model hint for the schema

    def get_serializer_class(self):
        return MyWorkspaceSerializer if self.request.method == "GET" else WorkspaceSerializer

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return Workspace.objects.none()
        return services.workspaces_for(self.request.user).prefetch_related("memberships__role")

    def perform_create(self, serializer):
        workspace = services.create_workspace(self.request.user, **serializer.validated_data)
        serializer.instance = workspace
        self.request.workspace = workspace
        audit.record(self.request, "create", workspace)


class WorkspaceDetailView(generics.RetrieveUpdateDestroyAPIView):
    """The workspace in the URL. Reading needs workspace.view, editing workspace.manage, deleting the Owner."""

    serializer_class = WorkspaceSerializer
    permission_classes = [IsAuthenticated, WorkspacePermission]
    http_method_names = ["get", "patch", "delete"]

    def required_permission(self, request):
        return "workspace.view" if request.method == "GET" else "workspace.manage"

    def get_object(self):
        return self.request.workspace

    def perform_update(self, serializer):
        before = audit.snapshot(serializer.instance)
        instance = serializer.save()
        if before.get("vat_registered") != instance.vat_registered:
            match_default_to_vat_status(instance)
        audit.record(self.request, "update", instance, audit.diff(before, audit.snapshot(instance)))

    def perform_destroy(self, instance):
        if not self.request.membership.is_owner:
            raise BusinessRuleError("Only the Owner can delete a workspace.")
        instance.is_active = False  # kept for records; it disappears from everyone's list
        instance.save(update_fields=["is_active", "updated_at"])
        audit.record(self.request, "delete", instance)


class WorkspaceContextView(generics.GenericAPIView):
    """The caller's role, permissions, employee record and in-charge modules in this workspace."""

    permission_classes = [IsAuthenticated, WorkspacePermission]
    serializer_class = WorkspaceContextSerializer

    def get(self, request, workspace):
        from apps.departments.models import Department
        from apps.fiscalyears.models import FiscalYear
        from apps.fiscalyears.services import ended_unclosed

        membership = request.membership
        employee = getattr(membership, "employee", None)
        in_charge = []
        if employee is not None:
            for dept in Department.objects.filter(workspace=request.workspace, head=employee):
                in_charge.extend(dept.modules)
        data = {
            "workspace": request.workspace,
            "membership_id": membership.id,
            "role": membership.role.name,
            "role_slug": membership.role.slug,
            "permissions": membership.role.permissions,
            "is_owner": membership.is_owner,
            "employee_id": employee.id if employee else None,
            "department": employee.department.name if employee and employee.department else None,
            "in_charge_of": sorted(set(in_charge)),
            "etims_enabled": settings.ETIMS_ENABLED,
            "fiscal_years": [
                {"id": str(y.id), "name": y.name, "start_date": y.start_date.isoformat(), "end_date": y.end_date.isoformat(), "status": y.status}
                for y in FiscalYear.objects.filter(workspace=request.workspace).order_by("-start_date")
            ],
            "unclosed_years": [y.name for y in ended_unclosed(request.workspace)],
        }
        return Response(self.get_serializer(data).data)
