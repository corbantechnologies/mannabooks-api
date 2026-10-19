from django.db.models import Count, Q
from rest_framework import generics
from rest_framework.response import Response

from apps.core.catalog import DEPARTMENT_MODULES, MODULES
from apps.core.exceptions import BusinessRuleError
from apps.core.tenancy import WorkspaceScopedMixin

from .models import Role
from .serializers import PermissionCatalogSerializer, RoleSerializer


class RoleQuerysetMixin(WorkspaceScopedMixin):
    module = "roles"
    queryset = Role.objects.none()  # model hint for the schema
    serializer_class = RoleSerializer

    def workspace_queryset(self):
        return (
            Role.objects.filter(workspace=self.request.workspace)
            .annotate(member_count=Count("memberships", filter=Q(memberships__status="active")))
            .order_by("name")
        )


class RoleListCreateView(RoleQuerysetMixin, generics.ListCreateAPIView):
    search_fields = ["name", "description"]
    ordering_fields = ["name", "created_at"]


class RoleDetailView(RoleQuerysetMixin, generics.RetrieveUpdateDestroyAPIView):
    http_method_names = ["get", "patch", "delete"]

    def perform_destroy(self, instance):
        if instance.is_preset:
            raise BusinessRuleError("Preset roles can't be deleted. Edit their permissions instead.")
        if instance.memberships.exists():
            raise BusinessRuleError("Move this role's members to another role before deleting it.")
        super().perform_destroy(instance)


class PermissionCatalogView(WorkspaceScopedMixin, generics.GenericAPIView):
    """Every permission a role can hold, and the modules a department can run."""

    serializer_class = PermissionCatalogSerializer

    def get(self, request, workspace):
        data = {
            "modules": [{"module": key, "label": spec["label"], "actions": spec["actions"]} for key, spec in MODULES.items()],
            "department_modules": DEPARTMENT_MODULES,
        }
        return Response(self.get_serializer(data).data)
