from django.utils import timezone
from drf_spectacular.utils import extend_schema
from rest_framework import generics, status
from rest_framework.response import Response

from apps.auditlogs import services as audit
from apps.core.tenancy import WorkspaceScopedMixin, workspace_object

from . import services
from .models import BankTransfer
from .serializers import BankTransferSerializer


class TransferMixin(WorkspaceScopedMixin):
    queryset = BankTransfer.objects.select_related("from_account", "to_account")
    serializer_class = BankTransferSerializer


class BankTransferListCreateView(TransferMixin, generics.ListCreateAPIView):
    permission_map = {"GET": "banking.view", "POST": "banking.transfer"}
    filterset_fields = ["status", "from_account", "to_account"]
    search_fields = ["number", "reference"]

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        d = serializer.validated_data
        t = services.create(request.workspace, from_account=d["from_account"], to_account=d["to_account"],
                            transfer_date=d.get("transfer_date") or timezone.localdate(), amount=d["amount"], fee=d.get("fee", 0),
                            reference=d.get("reference", ""), notes=d.get("notes", ""), user=request.user)
        audit.record(request, "create", t)
        return Response(BankTransferSerializer(t).data, status=status.HTTP_201_CREATED)


class BankTransferVoidView(TransferMixin, generics.GenericAPIView):
    permission_map = {"POST": "banking.transfer"}

    @extend_schema(request=None, responses={200: BankTransferSerializer})
    def post(self, request, workspace, pk):
        t = services.void(workspace_object(BankTransfer, request, pk=pk), request.user)
        audit.record(request, "other", t, {"void": True})
        return Response(BankTransferSerializer(t).data)
