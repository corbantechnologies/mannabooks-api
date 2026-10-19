from django.db.models import Count
from drf_spectacular.utils import OpenApiParameter, extend_schema, inline_serializer
from rest_framework import generics, serializers
from rest_framework.response import Response

from apps.core.exceptions import BusinessRuleError
from apps.core.tenancy import WorkspaceScopedMixin

from .models import PriceList
from .serializers import PriceListSerializer
from .services import prices_for


class PriceListMixin(WorkspaceScopedMixin):
    module = "products"
    queryset = PriceList.objects.prefetch_related("items__product")
    serializer_class = PriceListSerializer

    def workspace_queryset(self):
        return super().workspace_queryset().annotate(customer_count=Count("customers", distinct=True)).order_by("name")


class PriceListListCreateView(PriceListMixin, generics.ListCreateAPIView):
    filterset_fields = ["is_active"]
    search_fields = ["name"]


class PriceListDetailView(PriceListMixin, generics.RetrieveUpdateDestroyAPIView):
    http_method_names = ["get", "patch", "delete"]

    def perform_destroy(self, instance):
        if instance.customers.exists():
            raise BusinessRuleError("Customers use this price list. Move them to another list or deactivate it.")
        super().perform_destroy(instance)


class CustomerPricesView(WorkspaceScopedMixin, generics.GenericAPIView):
    """Every active product's price for one customer (their price list), for filling in sales lines."""

    permission_map = {"GET": "products.view"}
    queryset = PriceList.objects.all()
    pagination_class = None

    @extend_schema(
        parameters=[OpenApiParameter("customer", str, required=False, description="Customer id; blank for normal prices")],
        responses={200: inline_serializer("ProductPrice", {"product_id": serializers.UUIDField(), "price": serializers.DecimalField(max_digits=18, decimal_places=4)}, many=True)},
    )
    def get(self, request, workspace):
        from apps.customers.models import Customer

        price_list = None
        customer_id = request.query_params.get("customer")
        if customer_id:
            customer = Customer.objects.filter(workspace=request.workspace, pk=customer_id).select_related("price_list").first()
            price_list = customer.price_list if customer else None
        prices = prices_for(request.workspace, price_list)
        return Response([{"product_id": k, "price": str(v)} for k, v in prices.items()])
