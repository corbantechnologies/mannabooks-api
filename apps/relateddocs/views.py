from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import generics
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from apps.core.tenancy import WorkspaceScopedMixin
from apps.invoices.models import Invoice

from . import services
from .serializers import RelatedDocumentSerializer


class RelatedDocumentsView(WorkspaceScopedMixin, generics.GenericAPIView):
    """The chain a document belongs to, both ways, in the order of the process: what it came from and what came after it."""

    permission_map = {"GET": None}
    queryset = Invoice.objects.none()
    serializer_class = RelatedDocumentSerializer
    pagination_class = None

    @extend_schema(parameters=[OpenApiParameter("kind", OpenApiTypes.STR, required=True, enum=list(services.KINDS)),
                               OpenApiParameter("id", OpenApiTypes.UUID, required=True)],
                   responses={200: RelatedDocumentSerializer(many=True)})
    def get(self, request, workspace):
        kind = request.query_params.get("kind")
        if kind not in services.KINDS:
            raise ValidationError({"kind": ["Unknown document kind."]})
        try:
            rows = services.chain(request.workspace, kind, request.query_params.get("id"), request.membership)
        except (ValueError, Exception) as exc:  # noqa: BLE001 - a malformed id
            if isinstance(exc, ValidationError):
                raise
            rows = []
        return Response(RelatedDocumentSerializer(rows, many=True).data)
