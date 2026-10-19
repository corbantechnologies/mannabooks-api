from django.utils import timezone
from drf_spectacular.utils import extend_schema
from rest_framework import generics, status
from rest_framework.response import Response

from apps.auditlogs import services as audit
from apps.core.tenancy import WorkspaceScopedMixin, workspace_object

from . import services
from .models import FixedAsset
from .serializers import AssetActionSerializer, AssetScheduleSerializer, CategoryDefaultSerializer, FixedAssetSerializer


class AssetMixin(WorkspaceScopedMixin):
    module = "fixedassets"
    queryset = FixedAsset.objects.select_related("location", "custodian", "cost_center", "supplier", "bill", "asset_account", "accumulated_account",
                                                 "expense_account", "disposal_account")
    serializer_class = FixedAssetSerializer

    def respond(self, obj, code=status.HTTP_200_OK):
        return Response(FixedAssetSerializer(self.queryset.get(pk=obj.pk), context=self.get_serializer_context()).data, status=code)


class FixedAssetListCreateView(AssetMixin, generics.ListCreateAPIView):
    filterset_fields = ["status", "category", "location", "cost_center"]
    search_fields = ["number", "name", "serial_number"]

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        asset = services.save(request.workspace, data=dict(serializer.validated_data), user=request.user)
        audit.record(request, "create", asset)
        return self.respond(asset, status.HTTP_201_CREATED)


class FixedAssetDetailView(AssetMixin, generics.RetrieveUpdateDestroyAPIView):
    http_method_names = ["get", "patch", "delete"]

    def update(self, request, *args, **kwargs):
        asset = self.get_object()
        serializer = self.get_serializer(asset, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        asset = services.save(request.workspace, data=dict(serializer.validated_data), user=request.user, asset=asset)
        audit.record(request, "update", asset)
        return self.respond(asset)

    def perform_destroy(self, instance):
        audit.record(self.request, "delete", instance)
        services.delete(instance, self.request.user)


class FixedAssetActionView(AssetMixin, generics.GenericAPIView):
    """dispose (sold or scrapped, with any money received) or undo_disposal."""

    serializer_class = AssetActionSerializer

    @extend_schema(responses={200: FixedAssetSerializer})
    def post(self, request, workspace, pk):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        d = serializer.validated_data
        asset = workspace_object(FixedAsset, request, pk=pk)
        if d["action"] == "dispose":
            asset = services.dispose(asset, on=d.get("date") or timezone.localdate(), proceeds=d.get("proceeds") or 0,
                                     received_into=d.get("received_into"), user=request.user)
        else:
            asset = services.undo_disposal(asset, request.user)
        audit.record(request, "other", asset, {"action": d["action"]})
        return self.respond(asset)


class FixedAssetScheduleView(AssetMixin, generics.GenericAPIView):
    serializer_class = AssetScheduleSerializer

    def get(self, request, workspace, pk):
        asset = workspace_object(FixedAsset, request, pk=pk)
        history = list(asset.depreciation_entries.order_by("month_end").values("month_end", "amount"))
        return Response(AssetScheduleSerializer({"history": history, "projection": services.schedule(asset)}).data)


class CategoryDefaultsView(AssetMixin, generics.GenericAPIView):
    """The usual method, life and account for each category, to fill the form."""

    serializer_class = CategoryDefaultSerializer
    pagination_class = None

    @extend_schema(responses={200: CategoryDefaultSerializer(many=True)})
    def get(self, request, workspace):
        rows = []
        for value, label in FixedAsset.Category.choices:
            d = services.defaults_for(request.workspace, value)
            rows.append({"category": value, "label": label, "method": d["method"], "useful_life_months": d["useful_life_months"],
                         "rate_percent": d["rate_percent"], "asset_account_id": d["asset_account"].pk if d["asset_account"] else None})
        return Response(CategoryDefaultSerializer(rows, many=True).data)
