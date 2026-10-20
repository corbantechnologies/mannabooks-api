from rest_framework import generics

from apps.core.tenancy import WorkspaceScopedMixin

from .models import PaymentOption
from .serializers import PaymentOptionSerializer


class OptionMixin(WorkspaceScopedMixin):
    """Everyone in the workspace sees them (they print on documents); workspace.manage changes them."""

    permission_map = {"GET": None, "POST": "workspace.manage", "PATCH": "workspace.manage", "DELETE": "workspace.manage"}
    queryset = PaymentOption.objects.all()
    serializer_class = PaymentOptionSerializer


class PaymentOptionListCreateView(OptionMixin, generics.ListCreateAPIView):
    pagination_class = None


class PaymentOptionDetailView(OptionMixin, generics.RetrieveUpdateDestroyAPIView):
    http_method_names = ["get", "patch", "delete"]
