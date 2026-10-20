from django.shortcuts import get_object_or_404
from django.utils import timezone
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import generics, status
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.core.exceptions import BusinessRuleError
from apps.intercompanytransactions import services as ic
from apps.intercompanytransactions.models import IntercompanyTransaction
from apps.ledgeraccounts.models import LedgerAccount
from apps.ledgeraccounts.views import parse_date
from apps.reports.views import _range
from apps.workspaces.models import Workspace

from . import services
from .models import CompanyGroup
from .serializers import (
    AddCompanySerializer,
    BalanceSerializer,
    CompanyGroupSerializer,
    ConsolidatedBSSerializer,
    ConsolidatedPLSerializer,
    IntercompanySerializer,
    IntercompanyVoidSerializer,
)


class GroupMixin:
    permission_classes = [IsAuthenticated]

    def group(self) -> CompanyGroup:
        return get_object_or_404(services.visible_groups(self.request.user), pk=self.kwargs["pk"])

    def reportable(self) -> CompanyGroup:
        group = self.group()
        missing = services.can_report(self.request.user, group)
        if missing:
            raise PermissionDenied(f"You can't see the reports of {', '.join(missing)}, so the group's reports are hidden.")
        return group


class GroupListCreateView(GroupMixin, generics.ListCreateAPIView):
    """Your company groups. Anyone signed in can start one; they become its owner."""

    serializer_class = CompanyGroupSerializer

    def get_queryset(self):
        return services.visible_groups(self.request.user).select_related("owner")

    def perform_create(self, serializer):
        serializer.save(owner=self.request.user)


class GroupDetailView(GroupMixin, generics.RetrieveUpdateDestroyAPIView):
    serializer_class = CompanyGroupSerializer
    http_method_names = ["get", "patch", "delete"]

    def get_object(self):
        return self.group()

    def perform_update(self, serializer):
        services.require_owner(self.request.user, serializer.instance)
        serializer.save()

    def perform_destroy(self, instance):
        services.require_owner(self.request.user, instance)
        if instance.transactions.filter(status="posted").exists():
            raise BusinessRuleError("The group has intercompany transactions. Void them first, or keep the group.")
        instance.workspaces.update(group=None)
        instance.delete()


class AddCompanyView(GroupMixin, generics.GenericAPIView):
    serializer_class = AddCompanySerializer

    @extend_schema(responses={200: CompanyGroupSerializer})
    def post(self, request, pk):
        group = self.group()
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        workspace = get_object_or_404(Workspace, slug=serializer.validated_data["workspace"], is_active=True)
        services.add_company(group, workspace, request.user)
        return Response(CompanyGroupSerializer(group, context={"request": request}).data)


class RemoveCompanyView(GroupMixin, generics.GenericAPIView):
    serializer_class = CompanyGroupSerializer

    def delete(self, request, pk, workspace):
        group = self.group()
        services.remove_company(group, get_object_or_404(Workspace, slug=workspace), request.user)
        return Response(CompanyGroupSerializer(group, context={"request": request}).data)


class ConsolidatedPLView(GroupMixin, generics.GenericAPIView):
    serializer_class = ConsolidatedPLSerializer

    @extend_schema(parameters=[OpenApiParameter("from", OpenApiTypes.DATE), OpenApiParameter("to", OpenApiTypes.DATE)])
    def get(self, request, pk):
        start, end = _range(request)
        return Response(ConsolidatedPLSerializer(services.consolidated_profit_and_loss(self.reportable(), from_date=start, to_date=end)).data)


class ConsolidatedBSView(GroupMixin, generics.GenericAPIView):
    serializer_class = ConsolidatedBSSerializer

    @extend_schema(parameters=[OpenApiParameter("as_of", OpenApiTypes.DATE)])
    def get(self, request, pk):
        as_of = parse_date(request.query_params.get("as_of"), "as_of") or timezone.localdate()
        return Response(ConsolidatedBSSerializer(services.consolidated_balance_sheet(self.reportable(), as_of=as_of)).data)


class IntercompanyListCreateView(GroupMixin, generics.ListCreateAPIView):
    """Sales, loans and settlements between the group's companies. Recording one posts both companies' entries."""

    serializer_class = IntercompanySerializer

    def get_queryset(self):
        return self.group().transactions.select_related("from_workspace", "to_workspace", "from_account", "to_account")

    def create(self, request, *args, **kwargs):
        group = self.group()
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        d = serializer.validated_data
        members = {ws.slug: ws for ws in services.companies(group)}
        src, dst = members.get(d["from_workspace"]), members.get(d["to_workspace"])
        if src is None or dst is None:
            raise BusinessRuleError("Choose two companies of this group.")
        t = ic.record(group, kind=d["kind"], from_workspace=src, to_workspace=dst, transaction_date=d.get("transaction_date"),
                      description=d["description"], amount=d["amount"],
                      from_account=get_object_or_404(LedgerAccount, pk=d["from_account_id"], workspace=src),
                      to_account=get_object_or_404(LedgerAccount, pk=d["to_account_id"], workspace=dst), user=request.user)
        return Response(IntercompanySerializer(t).data, status=status.HTTP_201_CREATED)


class IntercompanyVoidView(GroupMixin, generics.GenericAPIView):
    serializer_class = IntercompanyVoidSerializer

    @extend_schema(responses={200: IntercompanySerializer})
    def post(self, request, pk, tx):
        group = self.group()
        t = get_object_or_404(IntercompanyTransaction, pk=tx, group=group)
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return Response(IntercompanySerializer(ic.void(t, serializer.validated_data["reason"], request.user)).data)


class IntercompanyBalancesView(GroupMixin, generics.GenericAPIView):
    """Who owes whom inside the group, from the intercompany transactions."""

    serializer_class = BalanceSerializer
    pagination_class = None

    @extend_schema(responses={200: BalanceSerializer(many=True)})
    def get(self, request, pk):
        return Response(BalanceSerializer(ic.balances(self.group()), many=True).data)
