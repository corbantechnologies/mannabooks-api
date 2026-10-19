from drf_spectacular.utils import extend_schema
from rest_framework import generics, status
from rest_framework.response import Response

from apps.auditlogs import services as audit
from apps.core.exceptions import BusinessRuleError
from apps.core.tenancy import WorkspaceScopedMixin, workspace_object

from . import services
from .models import Bill
from .serializers import BillSerializer, BillVoidSerializer

HEADER = ("supplier", "supplier_invoice_number", "supplier_etims_number", "bill_date", "due_date", "purchase_order", "goods_receipt",
          "service_order", "warehouse", "prices_include_tax", "reference", "notes", "cost_center", "project")

class BillMixin(WorkspaceScopedMixin):
    queryset = Bill.objects.select_related("supplier", "purchase_order", "goods_receipt", "service_order").prefetch_related("lines__tax_rate", "lines__account", "lines__product")
    serializer_class = BillSerializer

    def obj(self):
        return workspace_object(self.queryset, self.request, pk=self.kwargs["pk"])

    def respond(self, obj, code=status.HTTP_200_OK):
        self.kwargs["pk"] = obj.pk
        return Response(BillSerializer(self.obj(), context=self.get_serializer_context()).data, status=code)


class BillListCreateView(BillMixin, generics.ListCreateAPIView):
    permission_map = {"GET": "bills.view", "POST": "bills.create"}
    filterset_fields = {"status": ["exact", "in"], "supplier": ["exact"], "bill_date": ["gte", "lte"], "due_date": ["lte"]}
    search_fields = ["number", "supplier__name", "supplier_invoice_number", "reference"]
    ordering_fields = ["bill_date", "due_date", "total", "balance_due"]

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        d = serializer.validated_data
        bill = services.save_draft(request.workspace, header={k: d[k] for k in HEADER if k in d}, rows=d.get("lines"), user=request.user)
        audit.record(request, "create", bill)
        return self.respond(bill, status.HTTP_201_CREATED)


class BillDetailView(BillMixin, generics.RetrieveUpdateDestroyAPIView):
    permission_map = {"GET": "bills.view", "PATCH": "bills.create", "DELETE": "bills.create"}
    http_method_names = ["get", "patch", "delete"]

    def get_object(self):
        return self.obj()

    def update(self, request, *args, **kwargs):
        bill = self.obj()
        serializer = self.get_serializer(bill, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        d = serializer.validated_data
        bill = services.save_draft(request.workspace, header={k: d[k] for k in HEADER if k in d}, rows=d.get("lines"), user=request.user, bill=bill)
        audit.record(request, "update", bill)
        return self.respond(bill)

    def perform_destroy(self, instance):
        if instance.status != Bill.Status.DRAFT:
            raise BusinessRuleError("Only drafts can be deleted. Void a posted bill instead.")
        super().perform_destroy(instance)


class BillPostView(BillMixin, generics.GenericAPIView):
    permission_map = {"POST": "bills.post"}

    @extend_schema(request=None, responses={200: BillSerializer})
    def post(self, request, workspace, pk):
        bill = services.post(self.obj(), request.user)
        audit.record(request, "other", bill, {"posted": bill.number})
        return self.respond(bill)


class BillVoidView(BillMixin, generics.GenericAPIView):
    permission_map = {"POST": "bills.void"}
    serializer_class = BillVoidSerializer

    @extend_schema(responses={200: BillSerializer})
    def post(self, request, workspace, pk):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        bill = services.void(self.obj(), serializer.validated_data["reason"], request.user)
        audit.record(request, "other", bill, {"void": serializer.validated_data["reason"]})
        return self.respond(bill)
