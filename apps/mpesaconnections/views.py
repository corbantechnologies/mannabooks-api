from django.utils import timezone
from drf_spectacular.utils import extend_schema
from rest_framework import generics
from rest_framework.response import Response

from apps.auditlogs import services as audit
from apps.core.exceptions import BusinessRuleError
from apps.core.tenancy import WorkspaceScopedMixin

from . import daraja
from .models import MpesaConnection
from .serializers import MpesaConnectionSerializer


class MpesaConnectionView(WorkspaceScopedMixin, generics.RetrieveUpdateAPIView):
    """The workspace's Daraja connection (one per workspace). PUT creates or replaces it."""

    module = "mpesa"
    queryset = MpesaConnection.objects.all()
    serializer_class = MpesaConnectionSerializer
    http_method_names = ["get", "put"]

    def get_object(self):
        return MpesaConnection.objects.filter(workspace=self.request.workspace).first() or MpesaConnection(workspace=self.request.workspace)

    def perform_update(self, serializer):
        is_new = serializer.instance.pk is None
        kwargs = {"workspace": self.request.workspace, "created_by": self.request.user} if is_new else {}
        instance = serializer.save(**kwargs)
        audit.record(self.request, "create" if is_new else "update", instance, {"shortcode": instance.shortcode})


class MpesaConnectionActionView(WorkspaceScopedMixin, generics.GenericAPIView):
    """`test`: check the credentials with Safaricom. `register`: ask Safaricom to send direct payments here."""

    permission_map = {"POST": "mpesa.manage"}
    queryset = MpesaConnection.objects.all()
    serializer_class = MpesaConnectionSerializer

    @extend_schema(request=None, responses={200: MpesaConnectionSerializer})
    def post(self, request, workspace, action):
        conn = MpesaConnection.objects.filter(workspace=request.workspace).first()
        if conn is None or not MpesaConnectionSerializer().get_has_credentials(conn):
            raise BusinessRuleError("Save your shortcode, consumer key, consumer secret and passkey first.")
        try:
            if action == "test":
                daraja.access_token(conn)
                conn.verified_at = timezone.now()
            else:
                daraja.register_c2b(conn)
                conn.c2b_registered_at = timezone.now()
            conn.last_error = ""
        except daraja.DarajaError as exc:
            conn.last_error = str(exc)[:255]
            conn.save(update_fields=["last_error", "updated_at"])
            raise BusinessRuleError(str(exc)) from exc
        conn.save()
        audit.record(request, "other", conn, {"action": action})
        return Response(self.get_serializer(conn).data)
