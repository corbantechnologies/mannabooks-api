from django.db.models import Case, DecimalField, Sum, When
from drf_spectacular.utils import extend_schema
from rest_framework import generics

from apps.core.exceptions import BusinessRuleError
from apps.core.tenancy import WorkspaceScopedMixin

from .models import Product
from .serializers import ProductBulkSerializer, ProductSerializer

MAX_BULK = 50


class ProductMixin(WorkspaceScopedMixin):
    module = "products"
    queryset = Product.objects.select_related("tax_rate", "category").prefetch_related("units")
    serializer_class = ProductSerializer

    def workspace_queryset(self):
        on_hand = Sum("stock_levels__quantity", output_field=DecimalField(max_digits=14, decimal_places=3))
        return super().workspace_queryset().annotate(
            stock_on_hand=Case(When(track_inventory=True, then=on_hand), default=None, output_field=DecimalField(max_digits=14, decimal_places=3)),
        ).order_by("name")


class ProductListCreateView(ProductMixin, generics.ListCreateAPIView):
    filterset_fields = ["is_active", "kind", "category", "track_inventory", "made_to_order"]
    search_fields = ["name", "code", "description"]
    ordering_fields = ["name", "code", "sale_price"]


class ProductDetailView(ProductMixin, generics.RetrieveUpdateDestroyAPIView):
    http_method_names = ["get", "patch", "delete"]

    def perform_destroy(self, instance):
        from apps.invoices.models import InvoiceLine
        from apps.quotations.models import QuotationLine
        from apps.receipts.models import ReceiptLine

        for model in (InvoiceLine, ReceiptLine, QuotationLine):
            if model.objects.filter(product=instance).exists():
                raise BusinessRuleError("This product is on documents. Deactivate it instead.")
        super().perform_destroy(instance)


class ProductBulkCreateView(ProductMixin, generics.GenericAPIView):
    """
    Up to 50 new products at once, each checked by the same rules as one product. All or nothing: if any row is wrong,
    nothing is saved and `errors` says which rows (by position) and why.
    """

    permission_map = {"POST": "products.manage"}
    serializer_class = ProductBulkSerializer
    pagination_class = None

    @extend_schema(request=ProductBulkSerializer, responses={201: ProductSerializer(many=True)})
    def post(self, request, workspace):
        from django.db import transaction
        from rest_framework import status
        from rest_framework.exceptions import ValidationError
        from rest_framework.response import Response

        from apps.auditlogs import services as audit

        rows = request.data.get("products") if isinstance(request.data, dict) else None
        if not isinstance(rows, list) or not rows:
            raise ValidationError({"products": ["Add at least one product."]})
        if len(rows) > MAX_BULK:
            raise ValidationError({"products": [f"Add up to {MAX_BULK} products at a time."]})
        context = self.get_serializer_context()
        serializers, errors, codes = [], {}, {}
        for n, row in enumerate(rows):
            s = ProductSerializer(data=row, context=context)
            if not s.is_valid():
                errors[n] = s.errors
            code = str(row.get("code") or "").strip().lower() if isinstance(row, dict) else ""
            if code:
                if code in codes:
                    errors.setdefault(n, {})["code"] = [f"Row {codes[code] + 1} uses this code too."]
                codes.setdefault(code, n)
            serializers.append(s)
        if errors:
            raise ValidationError({"rows": {str(n): e for n, e in errors.items()}})
        with transaction.atomic():
            made = [s.save(workspace=request.workspace, created_by=request.user) for s in serializers]
        for product in made:
            audit.record(request, "create", product)
        return Response(ProductSerializer(made, many=True, context=context).data, status=status.HTTP_201_CREATED)
