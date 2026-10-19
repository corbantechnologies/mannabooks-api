from rest_framework import generics

from apps.auditlogs import services as audit
from apps.core.tenancy import WorkspaceScopedMixin

from .models import LoyaltyProgram
from .serializers import LoyaltyProgramSerializer


class LoyaltyProgramView(WorkspaceScopedMixin, generics.RetrieveUpdateAPIView):
    """The workspace's loyalty programme settings. PUT creates or replaces them."""

    module = "loyalty"
    queryset = LoyaltyProgram.objects.all()
    serializer_class = LoyaltyProgramSerializer
    http_method_names = ["get", "put"]

    def get_object(self):
        return LoyaltyProgram.objects.filter(workspace=self.request.workspace).first() or LoyaltyProgram(workspace=self.request.workspace)

    def perform_update(self, serializer):
        is_new = serializer.instance.pk is None
        instance = serializer.save(**({"workspace": self.request.workspace, "created_by": self.request.user} if is_new else {}))
        audit.record(self.request, "create" if is_new else "update", instance)
