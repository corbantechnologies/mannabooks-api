from drf_spectacular.utils import extend_schema
from rest_framework import generics, status
from rest_framework.response import Response

from apps.auditlogs import services as audit
from apps.core.tenancy import WorkspaceScopedMixin, workspace_object

from . import services
from .models import PosShift
from .serializers import CloseShiftSerializer, PosShiftSerializer


class ShiftMixin(WorkspaceScopedMixin):
    queryset = PosShift.objects.select_related("register", "cashier")
    serializer_class = PosShiftSerializer

    def workspace_queryset(self):
        qs = super().workspace_queryset()
        if not self.request.membership.has_perm("pos.manage"):  # cashiers see their own shifts
            qs = qs.filter(cashier=self.request.user)
        return qs


class PosShiftListCreateView(ShiftMixin, generics.ListCreateAPIView):
    """Shifts. POST opens one for the caller on a till."""

    permission_map = {"GET": "pos.view", "POST": "pos.sell"}
    filterset_fields = ["status", "register"]

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        shift = services.open_shift(serializer.validated_data["register"], request.user, serializer.validated_data.get("opening_float"))
        audit.record(request, "create", shift)
        return Response(PosShiftSerializer(shift).data, status=status.HTTP_201_CREATED)


class CurrentShiftView(ShiftMixin, generics.GenericAPIView):
    """The caller's open shift, or 204 if they have none."""

    permission_map = {"GET": "pos.view"}

    @extend_schema(responses={200: PosShiftSerializer, 204: None})
    def get(self, request, workspace):
        shift = PosShift.objects.filter(workspace=request.workspace, cashier=request.user, status="open").select_related("register").first()
        return Response(PosShiftSerializer(shift).data) if shift else Response(status=status.HTTP_204_NO_CONTENT)


class PosShiftDetailView(ShiftMixin, generics.RetrieveAPIView):
    permission_map = {"GET": "pos.view"}


class CloseShiftView(ShiftMixin, generics.GenericAPIView):
    permission_map = {"POST": "pos.sell"}
    serializer_class = CloseShiftSerializer

    @extend_schema(responses={200: PosShiftSerializer})
    def post(self, request, workspace, pk):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        shift = workspace_object(self.workspace_queryset(), request, pk=pk)
        shift = services.close_shift(shift, serializer.validated_data["counted_cash"], serializer.validated_data.get("notes", ""), request.user)
        audit.record(request, "other", shift, {"closed": str(shift.counted_cash), "difference": str(shift.cash_difference)})
        return Response(PosShiftSerializer(shift).data)
