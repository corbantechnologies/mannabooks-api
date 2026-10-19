from django.db.models import Count
from rest_framework import generics

from apps.core.exceptions import BusinessRuleError
from apps.core.tenancy import WorkspaceScopedMixin

from .models import Department
from .serializers import DepartmentSerializer


class DepartmentMixin(WorkspaceScopedMixin):
    module = "departments"
    queryset = Department.objects.none()  # model hint for the schema
    serializer_class = DepartmentSerializer

    def workspace_queryset(self):
        return (
            Department.objects.filter(workspace=self.request.workspace)
            .select_related("head")
            .annotate(employee_count=Count("employees"))
            .order_by("name")
        )


class DepartmentListCreateView(DepartmentMixin, generics.ListCreateAPIView):
    filterset_fields = ["is_active"]
    search_fields = ["name", "code"]


class DepartmentDetailView(DepartmentMixin, generics.RetrieveUpdateDestroyAPIView):
    http_method_names = ["get", "patch", "delete"]

    def perform_destroy(self, instance):
        if instance.employees.exists():
            raise BusinessRuleError("Move this department's employees elsewhere before deleting it.")
        super().perform_destroy(instance)
