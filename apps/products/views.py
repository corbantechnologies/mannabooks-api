from django.db.models import Case, DecimalField, Sum, When
from rest_framework import generics

from apps.core.exceptions import BusinessRuleError
from apps.core.tenancy import WorkspaceScopedMixin

from .models import Product
from .serializers import ProductSerializer


class ProductMixin(WorkspaceScopedMixin):
    module = "products"
    queryset = Product.objects.select_related("tax_rate", "category")
    serializer_class = ProductSerializer

    def workspace_queryset(self):
        on_hand = Sum("stock_levels__quantity", output_field=DecimalField(max_digits=14, decimal_places=3))
        return super().workspace_queryset().annotate(
            stock_on_hand=Case(When(track_inventory=True, then=on_hand), default=None, output_field=DecimalField(max_digits=14, decimal_places=3)),
        ).order_by("name")


class ProductListCreateView(ProductMixin, generics.ListCreateAPIView):
    filterset_fields = ["is_active", "kind", "category", "track_inventory"]
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
