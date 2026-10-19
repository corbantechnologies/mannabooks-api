from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import generics
from rest_framework.response import Response

from apps.core.exceptions import BusinessRuleError
from apps.core.tenancy import WorkspaceScopedMixin
from apps.ledgeraccounts.views import parse_date
from apps.sequences.services import next_value

from . import services
from .models import Customer
from .serializers import CustomerSerializer, StatementSerializer


class CustomerMixin(WorkspaceScopedMixin):
    module = "customers"
    queryset = Customer.objects.all()
    serializer_class = CustomerSerializer

    def workspace_queryset(self):
        return services.with_balance(super().workspace_queryset()).order_by("name")


class CustomerListCreateView(CustomerMixin, generics.ListCreateAPIView):
    filterset_fields = ["is_active", "kind"]
    search_fields = ["name", "number", "email", "phone", "kra_pin"]
    ordering_fields = ["name", "number", "created_at"]

    def perform_create(self, serializer):
        serializer.validated_data["number"] = next_value(self.request.workspace, "customer")
        super().perform_create(serializer)
        serializer.instance = self.workspace_queryset().get(pk=serializer.instance.pk)


class CustomerDetailView(CustomerMixin, generics.RetrieveUpdateDestroyAPIView):
    http_method_names = ["get", "patch", "delete"]

    def perform_destroy(self, instance):
        from apps.invoices.models import Invoice
        from apps.payments.models import Payment
        from apps.quotations.models import Quotation

        for model in (Invoice, Payment, Quotation):
            if model.objects.filter(customer=instance).exists():
                raise BusinessRuleError("This customer has documents. Deactivate them instead.")
        super().perform_destroy(instance)


class CustomerStatementView(CustomerMixin, generics.GenericAPIView):
    serializer_class = StatementSerializer

    @extend_schema(parameters=[OpenApiParameter("from", OpenApiTypes.DATE), OpenApiParameter("to", OpenApiTypes.DATE)])
    def get(self, request, workspace, pk):
        customer = self.get_queryset().filter(pk=pk).first()
        if customer is None:
            from rest_framework.exceptions import NotFound

            raise NotFound()
        data = services.statement(customer, parse_date(request.query_params.get("from"), "from"), parse_date(request.query_params.get("to"), "to"))
        return Response(self.get_serializer({"customer": customer, **data}).data)
