from django.db.models import ProtectedError
from rest_framework import generics

from apps.core.exceptions import BusinessRuleError
from apps.core.tenancy import WorkspaceScopedMixin

from .models import CostCenter
from .serializers import CostCenterSerializer


class CostCenterMixin(WorkspaceScopedMixin):
    """Anyone in the workspace can read cost centres (documents pick them); budgets.manage changes them."""

    permission_map = {"GET": None, "POST": "budgets.manage", "PATCH": "budgets.manage", "DELETE": "budgets.manage"}
    queryset = CostCenter.objects.select_related("department")
    serializer_class = CostCenterSerializer


class CostCenterListCreateView(CostCenterMixin, generics.ListCreateAPIView):
    filterset_fields = ["is_active", "department"]
    search_fields = ["code", "name"]
    pagination_class = None


class CostCenterDetailView(CostCenterMixin, generics.RetrieveUpdateDestroyAPIView):
    http_method_names = ["get", "patch", "delete"]

    def perform_destroy(self, instance):
        try:
            super().perform_destroy(instance)
        except ProtectedError as exc:
            raise BusinessRuleError("This cost centre is used on documents or budgets. Make it inactive instead.") from exc
