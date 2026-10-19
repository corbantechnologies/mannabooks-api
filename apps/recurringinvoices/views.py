from drf_spectacular.utils import extend_schema
from rest_framework import generics, status
from rest_framework.response import Response

from apps.auditlogs import services as audit
from apps.core.exceptions import BusinessRuleError
from apps.core.tenancy import WorkspaceScopedMixin, workspace_object

from . import services
from .models import RecurringInvoice
from .serializers import RecurringActionSerializer, RecurringInvoiceSerializer

HEADER = ("name", "customer", "frequency", "start_date", "end_date", "auto_issue", "prices_include_tax", "reference", "notes")


class RecurringMixin(WorkspaceScopedMixin):
    module = "recurringinvoices"
    queryset = RecurringInvoice.objects.select_related("customer", "last_invoice").prefetch_related("lines")
    serializer_class = RecurringInvoiceSerializer

    def template(self):
        return workspace_object(self.queryset, self.request, pk=self.kwargs["pk"])

    def respond(self, template, code=status.HTTP_200_OK):
        self.kwargs["pk"] = template.pk
        return Response(RecurringInvoiceSerializer(self.template(), context=self.get_serializer_context()).data, status=code)


class RecurringListCreateView(RecurringMixin, generics.ListCreateAPIView):
    filterset_fields = ["status", "customer", "frequency"]
    search_fields = ["name", "customer__name"]
    ordering_fields = ["next_run_date", "name"]

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        d = serializer.validated_data
        template = services.save(request.workspace, data={k: d[k] for k in HEADER if k in d}, rows=d.get("lines", []), user=request.user)
        audit.record(request, "create", template)
        services.run_template(template)  # a start date of today or earlier raises the first invoice now
        return self.respond(template, status.HTTP_201_CREATED)


class RecurringDetailView(RecurringMixin, generics.RetrieveUpdateDestroyAPIView):
    http_method_names = ["get", "patch", "delete"]

    def get_object(self):
        return self.template()

    def update(self, request, *args, **kwargs):
        template = self.template()
        if template.status == RecurringInvoice.Status.ENDED:
            raise BusinessRuleError("This schedule has ended. Create a new one.")
        serializer = self.get_serializer(template, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        d = serializer.validated_data
        template = services.save(request.workspace, data={k: d[k] for k in HEADER if k in d}, rows=d.get("lines"), user=request.user, template=template)
        audit.record(request, "update", template)
        return self.respond(template)


class RecurringActionView(RecurringMixin, generics.GenericAPIView):
    serializer_class = RecurringActionSerializer

    @extend_schema(responses={200: RecurringInvoiceSerializer})
    def post(self, request, workspace, pk):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        action, template = serializer.validated_data["action"], self.template()
        S = RecurringInvoice.Status
        if action == "run":
            if template.status != S.ACTIVE:
                raise BusinessRuleError("Resume the schedule first.")
            services.raise_invoice(template, template.next_run_date, request.user)
        else:
            allowed = {"pause": (S.ACTIVE,), "resume": (S.PAUSED,), "end": (S.ACTIVE, S.PAUSED)}[action]
            if template.status not in allowed:
                raise BusinessRuleError(f"A {template.get_status_display().lower()} schedule can't be {action}d.")
            template.status = {"pause": S.PAUSED, "resume": S.ACTIVE, "end": S.ENDED}[action]
            template.save(update_fields=["status", "updated_at"])
        audit.record(request, "other", template, {"action": action})
        return self.respond(template)
