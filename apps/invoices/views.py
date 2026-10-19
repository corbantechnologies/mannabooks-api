from drf_spectacular.utils import extend_schema
from rest_framework import generics, status
from rest_framework.response import Response

from apps.auditlogs import services as audit
from apps.core.exceptions import BusinessRuleError
from apps.core.sales_views import header_from
from apps.core.tenancy import WorkspaceScopedMixin, workspace_object

from . import services
from .models import Invoice
from .serializers import InvoiceSerializer, VoidSerializer


class InvoiceMixin(WorkspaceScopedMixin):
    queryset = Invoice.objects.select_related("customer").prefetch_related("lines__tax_rate", "lines__account")
    serializer_class = InvoiceSerializer

    def invoice(self):
        return workspace_object(self.queryset, self.request, pk=self.kwargs["pk"])

    def respond(self, invoice, code=status.HTTP_200_OK):
        self.kwargs["pk"] = invoice.pk
        return Response(self.get_serializer(self.invoice()).data, status=code)


class InvoiceListCreateView(InvoiceMixin, generics.ListCreateAPIView):
    permission_map = {"GET": "invoices.view", "POST": "invoices.create"}
    filterset_fields = {"kind": ["exact"], "status": ["exact", "in"], "customer": ["exact"], "issue_date": ["gte", "lte"], "due_date": ["lte"]}
    search_fields = ["number", "customer__name", "reference"]
    ordering_fields = ["issue_date", "due_date", "number", "total", "balance_due"]

    def get_serializer_context(self):
        return {**super().get_serializer_context(), "list": self.request.method == "GET"}

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        header = header_from(data, request.workspace)
        for key in ("due_date", "kind", "original_invoice"):
            if key in data:
                header[key] = data[key]
        invoice = services.save_draft(request.workspace, header=header, rows=data.get("lines", []), user=request.user)
        audit.record(request, "create", invoice)
        return self.respond(invoice, status.HTTP_201_CREATED)


class InvoiceDetailView(InvoiceMixin, generics.RetrieveUpdateDestroyAPIView):
    permission_map = {"GET": "invoices.view", "PATCH": "invoices.create", "DELETE": "invoices.create"}
    http_method_names = ["get", "patch", "delete"]

    def get_object(self):
        return self.invoice()

    def update(self, request, *args, **kwargs):
        invoice = self.invoice()
        serializer = self.get_serializer(invoice, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        header = header_from(data, request.workspace)
        for key in ("due_date", "original_invoice"):
            if key in data:
                header[key] = data[key]
        before = audit.snapshot(invoice)
        invoice = services.save_draft(request.workspace, header=header, rows=data.get("lines"), user=request.user, invoice=invoice)
        audit.record(request, "update", invoice, audit.diff(before, audit.snapshot(invoice)))
        return self.respond(invoice)

    def perform_destroy(self, instance):
        if instance.status != Invoice.Status.DRAFT:
            raise BusinessRuleError("Only drafts can be deleted. Void an issued invoice instead.")
        super().perform_destroy(instance)


class InvoiceIssueView(InvoiceMixin, generics.GenericAPIView):
    permission_map = {"POST": "invoices.issue"}

    @extend_schema(request=None, responses={200: InvoiceSerializer})
    def post(self, request, workspace, pk):
        invoice = services.issue(self.invoice(), request.user)
        audit.record(request, "other", invoice, {"issued": invoice.number})
        return self.respond(invoice)


class InvoiceVoidView(InvoiceMixin, generics.GenericAPIView):
    permission_map = {"POST": "invoices.void"}

    @extend_schema(request=VoidSerializer, responses={200: InvoiceSerializer})
    def post(self, request, workspace, pk):
        serializer = VoidSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        invoice = services.void(self.invoice(), serializer.validated_data["reason"], request.user)
        audit.record(request, "other", invoice, {"void": serializer.validated_data["reason"]})
        return self.respond(invoice)
