from django.utils import timezone
from drf_spectacular.utils import extend_schema
from rest_framework import generics, status
from rest_framework.response import Response

from apps.auditlogs import services as audit
from apps.core.tenancy import WorkspaceScopedMixin, workspace_object

from . import services
from .models import OtherIncome
from .serializers import IncomeVoidSerializer, OtherIncomeSerializer


class IncomeMixin(WorkspaceScopedMixin):
    queryset = OtherIncome.objects.select_related("received_into").prefetch_related("lines__account")
    serializer_class = OtherIncomeSerializer

    def respond(self, obj, code=status.HTTP_200_OK):
        return Response(OtherIncomeSerializer(self.get_queryset().get(pk=obj.pk), context=self.get_serializer_context()).data, status=code)


class OtherIncomeListCreateView(IncomeMixin, generics.ListCreateAPIView):
    permission_map = {"GET": "banking.view", "POST": "banking.receive"}
    filterset_fields = {"status": ["exact"], "received_into": ["exact"], "income_date": ["gte", "lte"]}
    search_fields = ["number", "payer", "reference"]

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        d = serializer.validated_data
        income = services.create(request.workspace, received_into=d["received_into"], income_date=d.get("income_date") or timezone.localdate(),
                                 rows=d["lines"], prices_include_tax=d.get("prices_include_tax", True), user=request.user,
                                 **{k: d[k] for k in ("payer", "reference", "notes", "cost_center", "project") if k in d})
        audit.record(request, "create", income)
        return self.respond(income, status.HTTP_201_CREATED)


class OtherIncomeDetailView(IncomeMixin, generics.RetrieveAPIView):
    permission_map = {"GET": "banking.view"}


class OtherIncomeVoidView(IncomeMixin, generics.GenericAPIView):
    permission_map = {"POST": "banking.receive"}
    serializer_class = IncomeVoidSerializer

    @extend_schema(responses={200: OtherIncomeSerializer})
    def post(self, request, workspace, pk):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        income = services.void(workspace_object(OtherIncome, request, pk=pk), serializer.validated_data["reason"], request.user)
        audit.record(request, "other", income, {"void": serializer.validated_data["reason"]})
        return self.respond(income)
