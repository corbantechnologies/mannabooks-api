from rest_framework import generics

from apps.core.tenancy import WorkspaceScopedMixin

from .models import StatutoryRate
from .serializers import StatutoryRateSerializer
from .services import seed


class RateMixin(WorkspaceScopedMixin):
    permission_map = {"GET": "payroll.view", "POST": "payroll.manage", "PATCH": "payroll.manage", "DELETE": "payroll.manage"}
    queryset = StatutoryRate.objects.all()
    serializer_class = StatutoryRateSerializer


class StatutoryRateListCreateView(RateMixin, generics.ListCreateAPIView):
    """Rate sets by date. The first visit adds the rates MannaBooks knows."""

    def list(self, request, *args, **kwargs):
        seed(request.workspace)
        return super().list(request, *args, **kwargs)


class StatutoryRateDetailView(RateMixin, generics.RetrieveUpdateDestroyAPIView):
    http_method_names = ["get", "patch", "delete"]
