from rest_framework import generics

from apps.core.tenancy import WorkspaceScopedMixin

from .models import AuditLog
from .serializers import AuditLogSerializer


class AuditLogListView(WorkspaceScopedMixin, generics.ListAPIView):
    module = "auditlogs"
    queryset = AuditLog.objects.select_related("actor")
    serializer_class = AuditLogSerializer
    filterset_fields = ["action", "model", "object_id", "actor"]
    search_fields = ["object_repr", "model"]
