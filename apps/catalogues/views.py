from django.db.models import F
from django.utils import timezone
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import generics, status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.auditlogs import services as audit
from apps.core.tenancy import WorkspaceScopedMixin
from apps.documentemails.pdfs import enabled as pdfs_enabled

from . import services
from .models import Catalogue
from .serializers import (
    CatalogueAnalyticsSerializer,
    CatalogueItemSerializer,
    CatalogueQuoteLinkSerializer,
    CatalogueQuoteRequestSerializer,
    CatalogueSerializer,
    PublicCatalogueSerializer,
    SendCatalogueSerializer,
    SharedQuoteAnswerSerializer,
    SharedQuoteSerializer,
)


class CatalogueMixin(WorkspaceScopedMixin):
    module = "quotations"
    queryset = Catalogue.objects.select_related("customer", "price_list").prefetch_related("categories", "products", "excluded_products")
    serializer_class = CatalogueSerializer


class CatalogueListCreateView(CatalogueMixin, generics.ListCreateAPIView):
    """Product lists shared by private link. A client's picks become a quotation."""

    filterset_fields = ["customer", "is_active"]
    search_fields = ["name", "customer__name"]

    def perform_create(self, serializer):
        catalogue = serializer.save(workspace=self.request.workspace, created_by=self.request.user)
        audit.record(self.request, "create", catalogue)


class CatalogueDetailView(CatalogueMixin, generics.RetrieveUpdateDestroyAPIView):
    http_method_names = ["get", "patch", "delete"]

    def perform_update(self, serializer):
        audit.record(self.request, "update", serializer.save())


class CatalogueItemsView(CatalogueMixin, generics.GenericAPIView):
    """The products the catalogue shows right now, as the client sees them."""

    serializer_class = CatalogueItemSerializer
    pagination_class = None

    @extend_schema(responses={200: CatalogueItemSerializer(many=True)})
    def get(self, request, workspace, pk):
        return Response(CatalogueItemSerializer(services.items(self.get_object()), many=True).data)


class CatalogueSendView(CatalogueMixin, generics.GenericAPIView):
    """Email the link to the client."""

    permission_map = {"POST": "quotations.manage"}
    serializer_class = SendCatalogueSerializer

    @extend_schema(responses={202: None})
    def post(self, request, workspace, pk):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        catalogue = self.get_object()
        services.send_link(catalogue, to=serializer.validated_data["to"], message=serializer.validated_data["message"], user=request.user)
        audit.record(request, "other", catalogue, {"emailed": ", ".join(serializer.validated_data["to"])})
        return Response(status=status.HTTP_202_ACCEPTED)


def pdf_response(catalogue):
    from django.http import HttpResponse

    res = HttpResponse(services.pdf(catalogue), content_type="application/pdf")
    res["Content-Disposition"] = f'inline; filename="{services.pdf_filename(catalogue)}"'
    return res


class CataloguePdfView(CatalogueMixin, generics.GenericAPIView):
    """The catalogue as a PDF to print or send, with its link and a QR code."""

    @extend_schema(responses={(200, "application/pdf"): OpenApiTypes.BINARY})
    def get(self, request, workspace, pk):
        return pdf_response(self.get_object())


class CatalogueAnalyticsView(CatalogueMixin, generics.GenericAPIView):
    """Views, quote requests and wins per catalogue, and the products clients ask for most."""

    serializer_class = CatalogueAnalyticsSerializer

    @extend_schema(parameters=[OpenApiParameter("from", OpenApiTypes.DATE), OpenApiParameter("to", OpenApiTypes.DATE)],
                   responses={200: CatalogueAnalyticsSerializer})
    def get(self, request, workspace):
        from apps.ledgeraccounts.views import parse_date

        start, end = parse_date(request.query_params.get("from"), "from"), parse_date(request.query_params.get("to"), "to")
        return Response(CatalogueAnalyticsSerializer(services.analytics(request.workspace, start, end)).data)


# ---------------------------------------------------------------- the client's side (no sign-in)
class PublicMixin:
    permission_classes = [AllowAny]
    authentication_classes = []


class PublicCatalogueView(PublicMixin, APIView):
    @extend_schema(responses={200: PublicCatalogueSerializer})
    def get(self, request, token):
        c = services.open_catalogue(token)
        Catalogue.objects.filter(pk=c.pk).update(view_count=F("view_count") + 1, last_viewed_at=timezone.now())
        data = {"name": c.name, "intro": c.intro, "business": services.business_of(c.workspace),
                "customer_name": c.customer.name if c.customer_id else None, "show_prices": c.show_prices, "show_stock": c.show_stock,
                "reviews_first": c.reviews_first, "expires_on": c.expires_on, "pdf_available": pdfs_enabled(), "items": services.items(c)}
        return Response(PublicCatalogueSerializer(data).data)


class PublicCataloguePdfView(PublicMixin, APIView):
    @extend_schema(responses={(200, "application/pdf"): OpenApiTypes.BINARY})
    def get(self, request, token):
        return pdf_response(services.open_catalogue(token))


class PublicQuoteRequestView(PublicMixin, APIView):
    @extend_schema(request=CatalogueQuoteRequestSerializer, responses={201: CatalogueQuoteLinkSerializer})
    def post(self, request, token):
        c = services.open_catalogue(token)
        serializer = CatalogueQuoteRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        d = serializer.validated_data
        q = services.request_quote(c, name=d["name"], company=d["company"], phone=d["phone"], email=d["email"], notes=d["notes"],
                                   rows=[dict(r) for r in d["lines"]], wishes=[dict(w) for w in d["wishes"]])
        return Response({"token": q.public_token, "status": q.status}, status=status.HTTP_201_CREATED)


class PublicQuoteView(PublicMixin, APIView):
    @extend_schema(responses={200: SharedQuoteSerializer})
    def get(self, request, token):
        return Response(SharedQuoteSerializer(services.quote_data(services.open_quote(token))).data)


class PublicQuoteAnswerView(PublicMixin, APIView):
    @extend_schema(request=SharedQuoteAnswerSerializer, responses={200: SharedQuoteSerializer})
    def post(self, request, token):
        serializer = SharedQuoteAnswerSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        q = services.answer(services.open_quote(token), serializer.validated_data["action"])
        return Response(SharedQuoteSerializer(services.quote_data(q)).data)
