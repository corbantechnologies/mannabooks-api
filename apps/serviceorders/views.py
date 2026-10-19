from drf_spectacular.utils import extend_schema
from rest_framework import generics, status
from rest_framework.response import Response

from apps.auditlogs import services as audit
from apps.core.exceptions import BusinessRuleError
from apps.core.tenancy import WorkspaceScopedMixin, workspace_object

from . import services
from .models import ServiceOrder
from .serializers import ServiceOrderActionSerializer, ServiceOrderSerializer

HEADER = ("supplier", "order_date", "required_by", "scope", "prices_include_tax", "reference", "notes", "cost_center", "project")

class ServiceOrderMixin(WorkspaceScopedMixin):
    queryset = ServiceOrder.objects.select_related("supplier", "approved_by").prefetch_related("lines__tax_rate", "lines__account", "lines__product")
    serializer_class = ServiceOrderSerializer

    def obj(self):
        return workspace_object(self.queryset, self.request, pk=self.kwargs["pk"])

    def respond(self, obj, code=status.HTTP_200_OK):
        self.kwargs["pk"] = obj.pk
        return Response(ServiceOrderSerializer(self.obj(), context=self.get_serializer_context()).data, status=code)


class ServiceOrderListCreateView(ServiceOrderMixin, generics.ListCreateAPIView):
    permission_map = {"GET": "purchaseorders.view", "POST": "purchaseorders.create"}
    filterset_fields = {"status": ["exact"], "supplier": ["exact"]}
    search_fields = ["number", "supplier__name", "scope"]

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        d = serializer.validated_data
        order = services.save(request.workspace, header={k: d[k] for k in HEADER if k in d}, rows=d.get("lines", []), user=request.user)
        audit.record(request, "create", order)
        return self.respond(order, status.HTTP_201_CREATED)


class ServiceOrderDetailView(ServiceOrderMixin, generics.RetrieveUpdateDestroyAPIView):
    permission_map = {"GET": "purchaseorders.view", "PATCH": "purchaseorders.create", "DELETE": "purchaseorders.create"}
    http_method_names = ["get", "patch", "delete"]

    def get_object(self):
        return self.obj()

    def update(self, request, *args, **kwargs):
        order = self.obj()
        serializer = self.get_serializer(order, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        d = serializer.validated_data
        order = services.save(request.workspace, header={k: d[k] for k in HEADER if k in d}, rows=d.get("lines"), user=request.user, order=order)
        return self.respond(order)

    def perform_destroy(self, instance):
        if instance.status != ServiceOrder.Status.DRAFT:
            raise BusinessRuleError("Only drafts can be deleted. Cancel the order instead.")
        super().perform_destroy(instance)


class ServiceOrderActionView(ServiceOrderMixin, generics.GenericAPIView):
    serializer_class = ServiceOrderActionSerializer

    def required_permission(self, request):
        return "purchaseorders.approve" if request.data.get("action") == "approve" else "purchaseorders.create"

    @extend_schema(responses={200: ServiceOrderSerializer})
    def post(self, request, workspace, pk):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        order = services.act(self.obj(), serializer.validated_data["action"], request.user)
        audit.record(request, "other", order, {"action": serializer.validated_data["action"]})
        return self.respond(order)
