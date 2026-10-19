from drf_spectacular.utils import extend_schema
from rest_framework import generics
from rest_framework.response import Response

from apps.auditlogs import services as audit
from apps.core.tenancy import WorkspaceScopedMixin

from . import services
from .models import EtimsDevice
from .serializers import EtimsDeviceSerializer


class EtimsDeviceView(WorkspaceScopedMixin, generics.RetrieveUpdateAPIView):
    """The workspace's eTIMS device settings (one per workspace). PUT creates or replaces them."""

    module = "etims"
    queryset = EtimsDevice.objects.all()
    serializer_class = EtimsDeviceSerializer
    http_method_names = ["get", "put"]

    def get_object(self):
        device = EtimsDevice.objects.filter(workspace=self.request.workspace).first()
        return device or EtimsDevice(workspace=self.request.workspace, kra_pin=self.request.workspace.kra_pin)

    def perform_update(self, serializer):
        is_new = serializer.instance.pk is None
        kwargs = {"workspace": self.request.workspace, "created_by": self.request.user} if is_new else {}
        instance = serializer.save(**kwargs)
        audit.record(self.request, "create" if is_new else "update", instance, {"device_serial": instance.device_serial})


class EtimsConnectView(WorkspaceScopedMixin, generics.GenericAPIView):
    """Initialise the OSCU with KRA. Only possible once eTIMS signing is switched on for the platform."""

    permission_map = {"POST": "etims.manage"}
    queryset = EtimsDevice.objects.all()
    serializer_class = EtimsDeviceSerializer

    @extend_schema(request=None, responses={200: EtimsDeviceSerializer})
    def post(self, request, workspace):
        device = EtimsDevice.objects.filter(workspace=request.workspace).first() or EtimsDevice(workspace=request.workspace)
        device = services.connect(device)
        audit.record(request, "other", device, {"connected": device.sdc_id})
        return Response(self.get_serializer(device).data)
