from django.utils import timezone
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import generics, status
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response

from apps.auditlogs import services as audit
from apps.core.tenancy import WorkspaceScopedMixin, workspace_object

from . import services
from .models import InboxMessage
from .serializers import (
    AcceptSerializer,
    DeclineSerializer,
    InboxMessageSerializer,
    InboxSendSerializer,
    PreviewSerializer,
)

# What the recipient needs to accept each kind, and what the sender needs to see the document they send.
ACCEPT_PERM = {"invoice": "bills.create", "quotation": "purchaseorders.create", "purchase_order": "invoices.create"}
VIEW_PERM = {"invoice": "invoices.view", "quotation": "quotations.view", "purchase_order": "purchaseorders.view"}


class InboxMixin(WorkspaceScopedMixin):
    module = "inbox"
    queryset = InboxMessage.objects.select_related("sent_by", "workspace")
    serializer_class = InboxMessageSerializer


class InboxListView(InboxMixin, generics.ListAPIView):
    """Documents other MannaBooks businesses sent to this one."""

    filterset_fields = ["status", "kind"]
    search_fields = ["number", "sender_name"]


class SentListView(InboxMixin, generics.ListAPIView):
    """Documents this business sent to others, with what they did with them."""

    permission_map = {"GET": "inbox.send"}
    filterset_fields = ["status", "kind"]
    search_fields = ["number"]

    def get_queryset(self):
        return InboxMessage.objects.filter(sender=self.request.workspace).select_related("sent_by", "workspace")


class InboxDetailView(InboxMixin, generics.RetrieveAPIView):
    def get_object(self):
        msg = workspace_object(InboxMessage, self.request, pk=self.kwargs["pk"])
        if msg.read_at is None:
            msg.read_at = timezone.now()
            msg.save(update_fields=["read_at", "updated_at"])
        return msg


class AcceptView(InboxMixin, generics.GenericAPIView):
    permission_map = {"POST": "inbox.manage"}
    serializer_class = AcceptSerializer

    @extend_schema(responses={200: InboxMessageSerializer})
    def post(self, request, workspace, pk):
        msg = workspace_object(InboxMessage, request, pk=pk)
        if not request.membership.has_perm(ACCEPT_PERM[msg.kind]):
            raise PermissionDenied("Your role can't create the draft this needs.")
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        msg = services.accept(msg, account=serializer.validated_data.get("account"), user=request.user)
        audit.record(request, "other", msg, {"status": msg.status, "created": msg.created_type})
        return Response(InboxMessageSerializer(msg).data)


class DeclineView(InboxMixin, generics.GenericAPIView):
    permission_map = {"POST": "inbox.manage"}
    serializer_class = DeclineSerializer

    @extend_schema(responses={200: InboxMessageSerializer})
    def post(self, request, workspace, pk):
        msg = workspace_object(InboxMessage, request, pk=pk)
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        msg = services.decline(msg, serializer.validated_data["reason"])
        audit.record(request, "other", msg, {"status": msg.status})
        return Response(InboxMessageSerializer(msg).data)


class PreviewView(InboxMixin, generics.GenericAPIView):
    """Whether a document's customer or supplier is on MannaBooks, so it can go straight to their inbox."""

    permission_map = {"GET": "inbox.send"}
    serializer_class = PreviewSerializer

    @extend_schema(parameters=[OpenApiParameter("kind", OpenApiTypes.STR, required=True), OpenApiParameter("document_id", OpenApiTypes.UUID, required=True)])
    def get(self, request, workspace):
        kind = request.query_params.get("kind", "")
        if kind not in VIEW_PERM:
            return Response({"detail": "Unknown kind."}, status=status.HTTP_400_BAD_REQUEST)
        return Response(PreviewSerializer(services.preview(request.workspace, kind, request.query_params.get("document_id"))).data)


class SendView(InboxMixin, generics.GenericAPIView):
    permission_map = {"POST": "inbox.send"}
    serializer_class = InboxSendSerializer

    @extend_schema(responses={201: InboxMessageSerializer})
    def post(self, request, workspace):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        d = serializer.validated_data
        if not request.membership.has_perm(VIEW_PERM[d["kind"]]):
            raise PermissionDenied()
        msg = services.send(request.workspace, d["kind"], d["document_id"], message=d.get("message", ""), user=request.user)
        audit.record(request, "other", msg, {"sent_to": msg.workspace.name})
        return Response(InboxMessageSerializer(msg).data, status=status.HTTP_201_CREATED)
