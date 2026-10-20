from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema
from rest_framework import generics, status
from rest_framework.response import Response

from apps.core.tenancy import WorkspaceScopedMixin

from . import services
from .models import SupportTicket
from .serializers import OpenTicketSerializer, ReplySerializer, SupportTicketSerializer


class SupportMixin(WorkspaceScopedMixin):
    """Help and feedback: anyone in the workspace, even when it is blocked or read-only. People see their own tickets."""

    permission_map = {"GET": None, "POST": None}
    subscription_exempt = True
    serializer_class = SupportTicketSerializer

    def get_queryset(self):
        return services.visible_to(self.request.user, staff=False).filter(workspace=self.request.workspace)


class TicketListCreateView(SupportMixin, generics.ListCreateAPIView):
    @extend_schema(request=OpenTicketSerializer, responses={201: SupportTicketSerializer})
    def post(self, request, workspace):
        s = OpenTicketSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        ticket = services.open_ticket(request.user, workspace=request.workspace, **s.validated_data)
        return Response(SupportTicketSerializer(ticket).data, status=status.HTTP_201_CREATED)


class TicketDetailView(SupportMixin, generics.RetrieveAPIView):
    pass


class TicketReplyView(SupportMixin, generics.GenericAPIView):
    serializer_class = ReplySerializer

    @extend_schema(responses={200: SupportTicketSerializer})
    def post(self, request, workspace, pk):
        ticket = get_object_or_404(self.get_queryset(), pk=pk)
        s = self.get_serializer(data=request.data)
        s.is_valid(raise_exception=True)
        ticket = services.reply(ticket, request.user, s.validated_data["body"], staff=False)
        return Response(SupportTicketSerializer(ticket).data)


class TicketCloseView(SupportMixin, generics.GenericAPIView):
    """The customer says it's sorted."""

    serializer_class = SupportTicketSerializer

    @extend_schema(request=None, responses={200: SupportTicketSerializer})
    def post(self, request, workspace, pk):
        from django.utils import timezone

        ticket = get_object_or_404(self.get_queryset(), pk=pk)
        ticket.status, ticket.resolved_at = SupportTicket.Status.RESOLVED, timezone.now()
        ticket.save(update_fields=["status", "resolved_at", "updated_at"])
        return Response(SupportTicketSerializer(ticket).data)
