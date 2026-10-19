from django.db.models import ProtectedError
from rest_framework import generics
from rest_framework.response import Response

from apps.core.exceptions import BusinessRuleError
from apps.core.tenancy import WorkspaceScopedMixin, workspace_object

from . import services
from .models import Project
from .serializers import ProjectSerializer, ProjectSummarySerializer


class ProjectMixin(WorkspaceScopedMixin):
    """Anyone in the workspace can list projects (documents pick them); projects.manage changes them."""

    permission_map = {"GET": None, "POST": "projects.manage", "PATCH": "projects.manage", "DELETE": "projects.manage"}
    queryset = Project.objects.select_related("customer", "manager")
    serializer_class = ProjectSerializer


class ProjectListCreateView(ProjectMixin, generics.ListCreateAPIView):
    filterset_fields = ["status", "customer"]
    search_fields = ["code", "name", "customer__name"]


class ProjectDetailView(ProjectMixin, generics.RetrieveUpdateDestroyAPIView):
    http_method_names = ["get", "patch", "delete"]

    def perform_destroy(self, instance):
        try:
            super().perform_destroy(instance)
        except ProtectedError as exc:
            raise BusinessRuleError("This project has transactions. Mark it completed or cancelled instead.") from exc


class ProjectSummaryView(WorkspaceScopedMixin, generics.GenericAPIView):
    """Income, costs and profit from the ledger lines tagged with the project."""

    permission_map = {"GET": "projects.view"}
    queryset = Project.objects.all()
    serializer_class = ProjectSummarySerializer

    def get(self, request, workspace, pk):
        return Response(ProjectSummarySerializer(services.summary(workspace_object(Project, request, pk=pk))).data)
