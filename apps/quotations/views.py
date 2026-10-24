from drf_spectacular.utils import extend_schema
from rest_framework import generics, status
from rest_framework.response import Response

from apps.auditlogs import services as audit
from apps.core.exceptions import BusinessRuleError
from apps.core.sales_views import header_from
from apps.core.tenancy import WorkspaceScopedMixin, workspace_object

from . import services
from .models import Quotation
from .serializers import ConvertedSerializer, QuotationActionSerializer, QuotationSerializer, ShareLinkSerializer


class QuotationMixin(WorkspaceScopedMixin):
    module = "quotations"
    queryset = Quotation.objects.select_related("customer").prefetch_related("lines__tax_rate", "lines__account")
    serializer_class = QuotationSerializer

    def quotation(self):
        return workspace_object(self.queryset, self.request, pk=self.kwargs["pk"])

    def respond(self, quotation, code=status.HTTP_200_OK):
        self.kwargs["pk"] = quotation.pk
        return Response(QuotationSerializer(self.quotation(), context=self.get_serializer_context()).data, status=code)

    @staticmethod
    def header(data, workspace):
        header = header_from(data, workspace)
        if "valid_until" in data:
            header["valid_until"] = data["valid_until"]
        return header


class QuotationListCreateView(QuotationMixin, generics.ListCreateAPIView):
    filterset_fields = {"status": ["exact"], "customer": ["exact"], "catalogue": ["exact"], "issue_date": ["gte", "lte"]}
    search_fields = ["number", "customer__name", "reference"]
    ordering_fields = ["issue_date", "number", "total"]

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        d = serializer.validated_data
        quotation = services.save(request.workspace, header=self.header(d, request.workspace), rows=d.get("lines", []), user=request.user)
        audit.record(request, "create", quotation)
        return self.respond(quotation, status.HTTP_201_CREATED)


class QuotationDetailView(QuotationMixin, generics.RetrieveUpdateDestroyAPIView):
    http_method_names = ["get", "patch", "delete"]

    def get_object(self):
        return self.quotation()

    def update(self, request, *args, **kwargs):
        quotation = self.quotation()
        serializer = self.get_serializer(quotation, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        d = serializer.validated_data
        quotation = services.save(request.workspace, header=self.header(d, request.workspace), rows=d.get("lines"), user=request.user, quotation=quotation)
        audit.record(request, "update", quotation)
        return self.respond(quotation)

    def perform_destroy(self, instance):
        if instance.status not in (Quotation.Status.DRAFT, Quotation.Status.DECLINED):
            raise BusinessRuleError("Only draft or declined quotations can be deleted.")
        super().perform_destroy(instance)


class QuotationActionView(QuotationMixin, generics.GenericAPIView):
    permission_map = {"POST": "quotations.manage"}
    serializer_class = QuotationActionSerializer

    @extend_schema(responses={200: QuotationSerializer})
    def post(self, request, workspace, pk):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        quotation = services.change_status(self.quotation(), serializer.validated_data["action"])
        audit.record(request, "other", quotation, {"status": quotation.status})
        return self.respond(quotation)


class QuotationConvertView(QuotationMixin, generics.GenericAPIView):
    permission_map = {"POST": "invoices.create"}
    serializer_class = ConvertedSerializer

    @extend_schema(request=None, responses={201: ConvertedSerializer})
    def post(self, request, workspace, pk):
        invoice = services.convert(self.quotation(), request.user)
        audit.record(request, "create", invoice)
        return Response({"invoice_id": str(invoice.id)}, status=status.HTTP_201_CREATED)


class QuotationShareView(QuotationMixin, generics.GenericAPIView):
    """A private link where the customer sees the quotation and accepts or declines it."""

    permission_map = {"POST": "quotations.manage"}
    serializer_class = ShareLinkSerializer

    @extend_schema(request=None, responses={200: ShareLinkSerializer})
    def post(self, request, workspace, pk):
        import secrets

        from apps.catalogues.services import public_url

        quotation = self.quotation()
        if not quotation.public_token:
            quotation.public_token = secrets.token_urlsafe(18)
            quotation.save(update_fields=["public_token", "updated_at"])
            audit.record(request, "other", quotation, {"shared": True})
        return Response({"url": public_url(quotation)})
