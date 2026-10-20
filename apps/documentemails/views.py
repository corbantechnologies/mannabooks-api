from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import generics, status
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError
from rest_framework.response import Response

from apps.auditlogs import services as audit
from apps.core.tenancy import WorkspaceScopedMixin

from . import services
from .models import DocumentEmail
from .registry import DOCS
from .serializers import DocumentEmailSerializer, DraftSerializer, SendSerializer

DOC_PARAMS = [OpenApiParameter("document_type", OpenApiTypes.STR, required=True, enum=list(DOCS)),
              OpenApiParameter("object_id", OpenApiTypes.UUID, required=True)]


def _document(request, doc_type, object_id, perm_attr="view_perm"):
    if doc_type not in DOCS:
        raise ValidationError({"document_type": ["Unknown document type."]})
    spec = DOCS[doc_type]
    if not request.membership.has_perm(getattr(spec, perm_attr)):
        raise PermissionDenied(f"Your role does not allow this ({getattr(spec, perm_attr)}).")
    try:
        document = spec.get(request.workspace, object_id)
    except Exception as exc:  # noqa: BLE001 - a malformed id
        raise NotFound("Document not found.") from exc
    if document is None:
        raise NotFound("Document not found.")
    return document


class DocumentEmailListCreateView(WorkspaceScopedMixin, generics.ListCreateAPIView):
    """GET: the emails sent for one document. POST: send a document by email."""

    permission_map = {"GET": None, "POST": None}
    queryset = DocumentEmail.objects.select_related("created_by")
    serializer_class = DocumentEmailSerializer
    pagination_class = None

    def get_serializer_class(self):
        return SendSerializer if self.request.method == "POST" else DocumentEmailSerializer

    @extend_schema(parameters=DOC_PARAMS)
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)

    def workspace_queryset(self):
        q = self.request.query_params
        document = _document(self.request, q.get("document_type"), q.get("object_id"))
        return super().workspace_queryset().filter(document_type=q.get("document_type"), object_id=document.pk)

    @extend_schema(request=SendSerializer, responses={201: DocumentEmailSerializer})
    def post(self, request, *args, **kwargs):
        serializer = SendSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        d = serializer.validated_data
        document = _document(request, d["document_type"], d["object_id"], "send_perm")
        email = services.send(request.workspace, doc_type=d["document_type"], document=document, to=d["to"], cc=d.get("cc", ""),
                              subject=d["subject"], message=d.get("message", ""), user=request.user)
        audit.record(request, "other", document, {"emailed_to": email.to})
        return Response(DocumentEmailSerializer(email).data, status=status.HTTP_201_CREATED)


class DocumentEmailDraftView(WorkspaceScopedMixin, generics.GenericAPIView):
    """The suggested To, subject and message for a document, to fill the send form."""

    permission_map = {"GET": None}
    queryset = DocumentEmail.objects.all()
    serializer_class = DraftSerializer

    @extend_schema(parameters=DOC_PARAMS)
    def get(self, request, workspace):
        q = request.query_params
        document = _document(request, q.get("document_type"), q.get("object_id"), "send_perm")
        return Response(DraftSerializer(services.defaults(request.workspace, q.get("document_type"), document)).data)
