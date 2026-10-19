from drf_spectacular.utils import extend_schema
from rest_framework import generics, status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response

from apps.core.exceptions import BusinessRuleError
from apps.core.tenancy import WorkspaceScopedMixin

from . import services
from .models import Invitation
from .serializers import AcceptedInvitationSerializer, InvitationPreviewSerializer, InvitationSerializer


class InvitationMixin(WorkspaceScopedMixin):
    module = "invitations"
    queryset = Invitation.objects.select_related("role", "created_by")
    serializer_class = InvitationSerializer


class InvitationListCreateView(InvitationMixin, generics.ListCreateAPIView):
    filterset_fields = ["status"]
    search_fields = ["email"]

    def perform_create(self, serializer):
        data = serializer.validated_data
        serializer.instance = services.invite(self.request, email=data["email"], role=data["role"])


class InvitationDetailView(InvitationMixin, generics.RetrieveDestroyAPIView):
    """Deleting a pending invitation revokes it; the record is kept."""

    def perform_destroy(self, instance):
        if instance.status != Invitation.Status.PENDING:
            raise BusinessRuleError("Only pending invitations can be revoked.")
        instance.status = Invitation.Status.REVOKED
        instance.save(update_fields=["status", "updated_at"])


class InvitationPreviewView(generics.RetrieveAPIView):
    """Public: the invitation behind a link, so the page can say who invited you to what."""

    permission_classes = [AllowAny]
    authentication_classes = []
    serializer_class = InvitationPreviewSerializer

    def get_object(self):
        return services.by_token(self.kwargs["token"])


class InvitationAcceptView(generics.GenericAPIView):
    """The signed-in user accepts an invitation sent to their email."""

    permission_classes = [IsAuthenticated]
    serializer_class = AcceptedInvitationSerializer

    @extend_schema(request=None, responses={200: AcceptedInvitationSerializer})
    def post(self, request, token):
        membership = services.accept(request, token)
        data = {"workspace_slug": membership.workspace.slug, "workspace_name": membership.workspace.name}
        return Response(self.get_serializer(data).data, status=status.HTTP_200_OK)
