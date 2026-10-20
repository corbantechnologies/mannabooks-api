from django.db.models import ProtectedError
from drf_spectacular.utils import extend_schema
from rest_framework import generics
from rest_framework.response import Response

from apps.auditlogs import services as audit
from apps.core.exceptions import BusinessRuleError
from apps.core.tenancy import WorkspaceScopedMixin, workspace_object
from apps.sequences.services import next_value

from . import services
from .models import Deal
from .serializers import DealMoveSerializer, DealSerializer, PipelineSerializer


class DealMixin(WorkspaceScopedMixin):
    module = "crm"
    queryset = Deal.objects.select_related("customer", "lead", "assigned_to__user", "quotation")
    serializer_class = DealSerializer


class DealListCreateView(DealMixin, generics.ListCreateAPIView):
    filterset_fields = {"stage": ["exact", "in"], "assigned_to": ["exact"], "customer": ["exact"], "lead": ["exact"],
                        "expected_close_date": ["gte", "lte"]}
    search_fields = ["number", "title", "customer__name", "lead__name", "lead__company"]
    ordering_fields = ["created_at", "value", "expected_close_date"]

    def perform_create(self, serializer):
        serializer.validated_data["number"] = next_value(self.request.workspace, "deal")
        lead = serializer.validated_data.get("lead")
        if lead is not None and not serializer.validated_data.get("customer") and lead.customer_id:
            serializer.validated_data["customer"] = lead.customer
        super().perform_create(serializer)
        if serializer.instance.quotation_id:
            services.quotation_saved(serializer.instance, serializer.instance.quotation)


class DealDetailView(DealMixin, generics.RetrieveUpdateDestroyAPIView):
    http_method_names = ["get", "patch", "delete"]

    def perform_update(self, serializer):
        before = serializer.instance.quotation_id
        super().perform_update(serializer)
        if serializer.instance.quotation_id and serializer.instance.quotation_id != before:
            services.quotation_saved(serializer.instance, serializer.instance.quotation)

    def perform_destroy(self, instance):
        try:
            super().perform_destroy(instance)
        except ProtectedError as exc:
            raise BusinessRuleError("This deal is linked to other records. Mark it lost instead.") from exc


class DealMoveView(DealMixin, generics.GenericAPIView):
    """Move a deal to another pipeline stage. Lost needs a reason."""

    permission_map = {"POST": "crm.manage"}
    serializer_class = DealMoveSerializer

    @extend_schema(responses={200: DealSerializer})
    def post(self, request, workspace, pk):
        deal = workspace_object(Deal, request, pk=pk)
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        services.move(deal, serializer.validated_data["stage"], lost_reason=serializer.validated_data.get("lost_reason", ""))
        audit.record(request, "other", deal, {"stage": deal.stage})
        return Response(DealSerializer(self.get_queryset().get(pk=pk), context=self.get_serializer_context()).data)


class PipelineView(DealMixin, generics.GenericAPIView):
    """Deals per stage with their value and weighted value; won this month and the win rate. `mine=true` for your own deals."""

    permission_map = {"GET": "crm.view"}
    serializer_class = PipelineSerializer

    def get(self, request, workspace):
        deals = self.get_queryset()
        if request.query_params.get("mine") == "true":
            deals = deals.filter(assigned_to=request.membership)
        return Response(PipelineSerializer(services.pipeline(request.workspace, deals)).data)
