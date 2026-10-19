from rest_framework import generics

from apps.core.exceptions import BusinessRuleError
from apps.core.tenancy import WorkspaceScopedMixin

from .models import PosRegister
from .serializers import PosRegisterSerializer


class RegisterMixin(WorkspaceScopedMixin):
    permission_map = {"GET": "pos.view", "POST": "pos.manage", "PATCH": "pos.manage", "DELETE": "pos.manage"}
    queryset = PosRegister.objects.select_related("branch").prefetch_related("shifts")
    serializer_class = PosRegisterSerializer


class PosRegisterListCreateView(RegisterMixin, generics.ListCreateAPIView):
    filterset_fields = ["is_active", "branch"]


class PosRegisterDetailView(RegisterMixin, generics.RetrieveUpdateDestroyAPIView):
    http_method_names = ["get", "patch", "delete"]

    def perform_destroy(self, instance):
        if instance.shifts.exists():
            raise BusinessRuleError("This till has shifts. Deactivate it instead.")
        super().perform_destroy(instance)
