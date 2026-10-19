from django.db import transaction
from drf_spectacular.utils import extend_schema
from rest_framework import generics
from rest_framework.response import Response

from apps.auditlogs import services as audit
from apps.core.exceptions import BusinessRuleError
from apps.core.tenancy import WorkspaceScopedMixin
from apps.fiscalyears.models import FiscalYear

from . import services
from .models import OpeningBalance
from .serializers import OpeningBalanceSerializer


class OpeningBalanceMixin(WorkspaceScopedMixin):
    module = "openingbalances"
    queryset = OpeningBalance.objects.all()
    serializer_class = OpeningBalanceSerializer

    def get_object(self):
        ob = OpeningBalance.objects.filter(workspace=self.request.workspace).prefetch_related("lines__account").first()
        if ob is None:
            first = FiscalYear.objects.filter(workspace=self.request.workspace).order_by("start_date").first()
            from datetime import timedelta

            as_of = (first.start_date - timedelta(days=1)) if first else None
            ob = OpeningBalance(workspace=self.request.workspace, as_of_date=as_of)
        return ob


class OpeningBalanceView(OpeningBalanceMixin, generics.RetrieveUpdateAPIView):
    """The workspace's single set of opening balances. PUT saves all lines as a draft."""

    http_method_names = ["get", "put"]

    @transaction.atomic
    def perform_update(self, serializer):
        ob = serializer.instance
        if ob.status == OpeningBalance.Status.POSTED:
            raise BusinessRuleError("Unpost the opening balances before changing them.")
        data = serializer.validated_data
        ob.as_of_date, ob.notes = data["as_of_date"], data.get("notes", "")
        if ob.pk is None:
            ob.created_by = self.request.user
        ob.save()
        services.save_lines(ob, data["lines"])
        audit.record(self.request, "update", ob, {"lines": len(data["lines"])})
        serializer.instance = self.get_object()


class OpeningBalancePostView(OpeningBalanceMixin, generics.GenericAPIView):
    @extend_schema(request=None, responses={200: OpeningBalanceSerializer})
    def post(self, request, workspace):
        ob = self.get_object()
        if ob.pk is None:
            raise BusinessRuleError("Enter and save the opening balances first.")
        services.post(ob, request.user)
        audit.record(request, "other", ob, {"status": "posted"})
        return Response(self.get_serializer(self.get_object()).data)


class OpeningBalanceUnpostView(OpeningBalanceMixin, generics.GenericAPIView):
    @extend_schema(request=None, responses={200: OpeningBalanceSerializer})
    def post(self, request, workspace):
        ob = self.get_object()
        if ob.pk is None:
            raise BusinessRuleError("There are no opening balances yet.")
        services.unpost(ob, request.user)
        audit.record(request, "other", ob, {"status": "draft"})
        return Response(self.get_serializer(self.get_object()).data)
