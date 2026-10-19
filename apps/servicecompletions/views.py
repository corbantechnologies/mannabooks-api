from django.db import transaction
from rest_framework import generics

from apps.auditlogs import services as audit
from apps.core.tenancy import WorkspaceScopedMixin
from apps.sequences.services import next_value

from .models import ServiceCompletion
from .serializers import ServiceCompletionSerializer


class CompletionMixin(WorkspaceScopedMixin):
    permission_map = {"GET": "purchaseorders.view", "POST": "purchaseorders.create"}
    queryset = ServiceCompletion.objects.select_related("service_order__supplier", "confirmed_by")
    serializer_class = ServiceCompletionSerializer


class ServiceCompletionListCreateView(CompletionMixin, generics.ListCreateAPIView):
    """Confirm work done. The service order becomes completed."""

    filterset_fields = ["service_order"]

    @transaction.atomic
    def perform_create(self, serializer):
        completion = serializer.save(workspace=self.request.workspace, created_by=self.request.user, confirmed_by=self.request.user,
                                     number=next_value(self.request.workspace, "service_completion"))
        order = completion.service_order
        order.status = "completed"
        order.save(update_fields=["status", "updated_at"])
        audit.record(self.request, "create", completion)


class ServiceCompletionDetailView(CompletionMixin, generics.RetrieveAPIView):
    pass
