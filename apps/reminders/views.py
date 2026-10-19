from drf_spectacular.utils import extend_schema
from rest_framework import generics, status
from rest_framework.response import Response

from apps.auditlogs import services as audit
from apps.core.tenancy import WorkspaceScopedMixin

from . import services
from .models import ReminderLog, ReminderRule
from .serializers import ReminderLogSerializer, ReminderRuleSerializer, SendReminderSerializer


class ReminderRuleListCreateView(WorkspaceScopedMixin, generics.ListCreateAPIView):
    """Reminder rules. Four inactive rules are created the first time they are listed."""

    module = "reminders"
    queryset = ReminderRule.objects.all()
    serializer_class = ReminderRuleSerializer

    def workspace_queryset(self):
        services.seed_rules(self.request.workspace)
        return super().workspace_queryset()


class ReminderRuleDetailView(WorkspaceScopedMixin, generics.RetrieveUpdateDestroyAPIView):
    module = "reminders"
    queryset = ReminderRule.objects.all()
    serializer_class = ReminderRuleSerializer
    http_method_names = ["get", "patch", "delete"]


class ReminderLogListView(WorkspaceScopedMixin, generics.ListAPIView):
    module = "reminders"
    queryset = ReminderLog.objects.select_related("invoice__customer", "rule")
    serializer_class = ReminderLogSerializer
    filterset_fields = ["invoice", "rule"]


class SendReminderView(WorkspaceScopedMixin, generics.GenericAPIView):
    """Email a reminder about one invoice now."""

    permission_map = {"POST": "invoices.view"}
    queryset = ReminderLog.objects.all()
    serializer_class = SendReminderSerializer

    @extend_schema(responses={201: ReminderLogSerializer})
    def post(self, request, workspace):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        log = services.send(serializer.validated_data["invoice"], user=request.user)
        audit.record(request, "other", log.invoice, {"reminder_sent_to": log.sent_to})
        return Response(ReminderLogSerializer(log).data, status=status.HTTP_201_CREATED)
