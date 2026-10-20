from django.db.models import Count, Q
from drf_spectacular.utils import extend_schema
from rest_framework import generics
from rest_framework.response import Response

from apps.auditlogs import services as audit
from apps.core.tenancy import WorkspaceScopedMixin, workspace_object
from apps.sequences.services import next_value

from . import services
from .models import Lead
from .serializers import LeadActionSerializer, LeadSerializer


class LeadMixin(WorkspaceScopedMixin):
    module = "crm"
    queryset = Lead.objects.select_related("assigned_to__user", "customer").annotate(
        open_tasks=Count("activities", filter=Q(activities__done_at__isnull=True)))
    serializer_class = LeadSerializer


class LeadListCreateView(LeadMixin, generics.ListCreateAPIView):
    filterset_fields = ["status", "source", "assigned_to"]
    search_fields = ["number", "name", "company", "phone", "email", "interest"]
    ordering_fields = ["created_at", "estimated_value", "name"]

    def perform_create(self, serializer):
        serializer.validated_data["number"] = next_value(self.request.workspace, "lead")
        super().perform_create(serializer)


class LeadDetailView(LeadMixin, generics.RetrieveUpdateDestroyAPIView):
    http_method_names = ["get", "patch", "delete"]


class LeadActionView(LeadMixin, generics.GenericAPIView):
    """Convert to a customer (and optionally open a deal), mark lost, or reopen."""

    permission_map = {"POST": "crm.manage"}
    serializer_class = LeadActionSerializer

    @extend_schema(responses={200: LeadSerializer})
    def post(self, request, workspace, pk):
        lead = workspace_object(Lead, request, pk=pk)
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        d = serializer.validated_data
        if d["action"] == "convert":
            services.convert(lead, customer=d.get("customer"), deal_title=d.get("deal_title", ""), deal_value=d.get("deal_value"), user=request.user)
        elif d["action"] == "lose":
            services.mark_lost(lead, d.get("reason", ""))
        else:
            services.reopen(lead)
        audit.record(request, "other", lead, {"action": d["action"]})
        return Response(LeadSerializer(self.get_queryset().get(pk=pk), context=self.get_serializer_context()).data)
