from drf_spectacular.utils import extend_schema
from rest_framework import generics, status
from rest_framework.response import Response

from apps.auditlogs import services as audit
from apps.core.tenancy import WorkspaceScopedMixin, workspace_object

from . import services
from .models import GoodsReceipt
from .serializers import GoodsReceiptSerializer, GoodsReceiptVoidSerializer


class ReceiptMixin(WorkspaceScopedMixin):
    queryset = GoodsReceipt.objects.select_related("supplier", "purchase_order", "warehouse").prefetch_related("lines")
    serializer_class = GoodsReceiptSerializer

    def obj(self):
        return workspace_object(self.queryset, self.request, pk=self.kwargs["pk"])

    def respond(self, obj, code=status.HTTP_200_OK):
        self.kwargs["pk"] = obj.pk
        return Response(GoodsReceiptSerializer(self.obj(), context=self.get_serializer_context()).data, status=code)


class GoodsReceiptListCreateView(ReceiptMixin, generics.ListCreateAPIView):
    """Goods received. Saving posts the stock straight away."""

    permission_map = {"GET": "goodsreceipts.view", "POST": "goodsreceipts.manage"}
    filterset_fields = {"status": ["exact"], "supplier": ["exact"], "purchase_order": ["exact"], "receipt_date": ["gte", "lte"]}
    search_fields = ["number", "supplier__name", "delivery_note_number"]

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        d = serializer.validated_data
        from django.utils import timezone

        grn = services.receive(request.workspace, supplier=d.get("supplier"), purchase_order=d.get("purchase_order"), warehouse=d.get("warehouse"),
                               receipt_date=d.get("receipt_date") or timezone.localdate(), rows=d["lines"],
                               delivery_note_number=d.get("delivery_note_number", ""), notes=d.get("notes", ""), user=request.user)
        audit.record(request, "create", grn)
        return self.respond(grn, status.HTTP_201_CREATED)


class GoodsReceiptDetailView(ReceiptMixin, generics.RetrieveAPIView):
    permission_map = {"GET": "goodsreceipts.view"}

    def get_object(self):
        return self.obj()


class GoodsReceiptVoidView(ReceiptMixin, generics.GenericAPIView):
    permission_map = {"POST": "goodsreceipts.manage"}
    serializer_class = GoodsReceiptVoidSerializer

    @extend_schema(responses={200: GoodsReceiptSerializer})
    def post(self, request, workspace, pk):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        grn = services.void(self.obj(), serializer.validated_data["reason"], request.user)
        audit.record(request, "other", grn, {"void": serializer.validated_data["reason"]})
        return self.respond(grn)
